from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.docker_lifecycle import docker_context, docker_executable, docker_runtime_status
from oma7.preflight import DEFAULT_RUNTIME_PINS
from oma7.release_candidate import build_default_release_candidate_readiness


def _emit(key: str, value: object) -> None:
    print(f"{key}={value}")


def _run_python_script(path: Path) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(path)], cwd=ROOT, capture_output=True, text=True, check=False)
    combined = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    return result.returncode, combined


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
    harness_rc, harness_output = _run_python_script(ROOT / "scripts" / "validate-harness.py")
    docker = None
    try:
        docker = docker_executable()
    except Exception:
        docker = None
    docker_ready, docker_reason = docker_runtime_status(docker) if docker else (False, "docker executable unavailable")
    pinned_ready = bool(docker_ready and docker_context(docker))
    host_rc, host_facts = _run_host_preflight()

    readiness = build_default_release_candidate_readiness(
        workspace=ROOT,
        harness_validation_ok=harness_rc == 0,
        docker_runtime_ready=docker_ready,
        pinned_runtime_ready=pinned_ready,
        auth_ready=host_facts.get("CODEX_AUTH_READY", "False") == "True",
    )

    _emit("HARNESS_VALIDATION_OK", harness_rc == 0)
    _emit("HARNESS_VALIDATION_OUTPUT", harness_output.replace("\n", " | "))
    _emit("DOCKER_RUNTIME_READY", docker_ready)
    _emit("DOCKER_RUNTIME_REASON", docker_reason)
    _emit("PINNED_CODEX_RUNTIME_READY", pinned_ready)
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
