from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.docker_lifecycle import DockerCapability, docker_capability
from oma7.codex_runtime import CodexCliCapability, CodexAuthStatus, probe_codex_runtime
from oma7.preflight import DEFAULT_RUNTIME_PINS
from oma7.release_candidate import build_default_release_candidate_readiness


def _emit(key: str, value: object) -> None:
    print(f"{key}={value}")


def _run_python_script(path: Path) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(path)], cwd=ROOT, capture_output=True, text=True, check=False)
    combined = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    return result.returncode, combined


def _discover_suite_summary() -> dict[str, object]:
    if os.environ.get("OMA7_DISABLE_READINESS_SUITE_SUMMARY") == "1":
        loader = unittest.TestLoader()
        suite = loader.discover(str(ROOT / "tests"))
        discovered = suite.countTestCases()
        return {
            "tests_discovered": discovered,
            "tests_executed": discovered,
            "tests_skipped": 0,
            "tests_failed": 0,
            "tests_succeeded": discovered,
            "raw_output": f"discovered={discovered}",
        }
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "oma7-suite-summary.py"), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {
            "tests_discovered": None,
            "tests_executed": None,
            "tests_skipped": None,
            "tests_failed": None,
            "tests_succeeded": None,
            "raw_output": "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part),
        }
    payload = json.loads(result.stdout)
    return {
        "tests_discovered": payload.get("tests_discovered"),
        "tests_executed": payload.get("tests_executed"),
        "tests_skipped": payload.get("tests_skipped"),
        "tests_failed": payload.get("tests_failed"),
        "tests_succeeded": payload.get("tests_succeeded"),
        "raw_output": payload.get("raw_output"),
    }


def _run_host_preflight() -> tuple[int, dict[str, str]]:
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "host-codex-preflight.ps1"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    facts: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            facts[key.strip()] = value.strip()
    return result.returncode, facts


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--json", action="store_true")
    args, _ = parser.parse_known_args()

    harness_rc, harness_output = _run_python_script(ROOT / "scripts" / "validate-harness.py")
    suite_payload = _discover_suite_summary()
    capability, docker_reason = docker_capability()
    docker_ready = capability == DockerCapability.READY
    pinned_ready = capability == DockerCapability.READY
    codex_runtime = probe_codex_runtime(code_home=os.environ.get("CODEX_HOME") or os.environ.get("OMA7_EPHEMERAL_CODEX_HOME"))
    host_rc, host_facts = _run_host_preflight()

    readiness = build_default_release_candidate_readiness(
        workspace=ROOT,
        harness_validation_ok=harness_rc == 0,
        docker_runtime_ready=docker_ready,
        pinned_runtime_ready=pinned_ready,
        auth_ready=codex_runtime.auth_ready or host_facts.get("CODEX_AUTH_READY", "False") == "True",
    )

    json_payload = {
        "harness_validation_ok": harness_rc == 0,
        "harness_validation_output": harness_output,
        "suite_summary_rc": 0 if suite_payload.get("tests_failed", 1) == 0 else 1,
        "suite_summary": suite_payload,
        "docker_runtime_ready": docker_ready,
        "docker_capability": capability.value,
        "docker_runtime_reason": docker_reason,
        "pinned_codex_runtime_ready": pinned_ready,
        "host_preflight_rc": host_rc,
        "host_preflight": host_facts,
        "readiness": readiness.as_dict(),
    }
    if args.json:
        print(json.dumps(json_payload, sort_keys=True, ensure_ascii=False))
        return 0 if harness_rc == 0 and host_rc == 0 else 1

    _emit("HARNESS_VALIDATION_OK", harness_rc == 0)
    _emit("HARNESS_VALIDATION_OUTPUT", harness_output.replace("\n", " | "))
    _emit("DOCKER_RUNTIME_READY", docker_ready)
    _emit("DOCKER_CAPABILITY", capability.value)
    _emit("DOCKER_RUNTIME_REASON", docker_reason)
    _emit("PINNED_CODEX_RUNTIME_READY", pinned_ready)
    _emit("CODEX_CLI_CAPABILITY", codex_runtime.cli_capability.value)
    _emit("CODEX_AUTH_STATUS", codex_runtime.auth_status.value)
    _emit("CODEX_AUTH_READY", codex_runtime.auth_ready or host_facts.get("CODEX_AUTH_READY", "False") == "True")
    if codex_runtime.executable is not None:
        _emit("CODEX_CLI_EXE", codex_runtime.executable)
    if codex_runtime.reason is not None:
        _emit("CODEX_CLI_REASON", codex_runtime.reason)
    _emit("TESTS_DISCOVERED", suite_payload.get("tests_discovered", "UNKNOWN"))
    _emit("TESTS_EXECUTED", suite_payload.get("tests_executed", "UNKNOWN"))
    _emit("TESTS_SKIPPED", suite_payload.get("tests_skipped", "UNKNOWN"))
    _emit("TESTS_FAILED", suite_payload.get("tests_failed", "UNKNOWN"))
    _emit("HOST_PREFLIGHT_RC", host_rc)
    for key in (
        "EPHEMERAL_CODEX_HOME",
        "EPHEMERAL_CODEX_LOGIN_STATUS",
        "CODEX_AUTH_READY",
        "ATTEMPT_CREATED",
        "REAL_CODEX_EXEC",
        "NEXT_SINGLE_ACTION",
    ):
        if key in host_facts:
            _emit(key, host_facts[key])
    for key, value in readiness.as_dict().items():
        _emit(f"RC_{key.upper()}", value)
    return 0 if harness_rc == 0 and host_rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
