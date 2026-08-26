from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Add project src to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.control_plane import new_attempt_identity
from oma7.codex_runtime import codex_executable, resolve_ephemeral_codex_home, run_codex_command, run_host_codex_preflight_probe
from oma7.preflight import DEFAULT_RUNTIME_PINS
from oma7.release_candidate import (
    REAL_EXECUTION_PREDICATE_KIND,
    ReleaseCandidateExecutionCapture,
    build_first_real_mission_spec,
    build_release_candidate_execution_evidence,
    persist_release_candidate_execution_artifacts,
)


def _resolve_ephemeral_codex_home() -> Path | None:
    raw = resolve_ephemeral_codex_home(environment=os.environ)
    if raw:
        return Path(raw)
    return None


def _runner_environment(codex_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    env["OMA7_EPHEMERAL_CODEX_HOME"] = str(codex_home)
    system_root = env.get("SystemRoot") or os.environ.get("SystemRoot") or r"C:\Windows"
    env.setdefault("SystemRoot", system_root)
    env.setdefault("WINDIR", system_root)
    env.setdefault("ComSpec", str(Path(system_root) / "System32" / "cmd.exe"))
    userprofile = env.get("USERPROFILE")
    if userprofile:
        env.setdefault("HOME", userprofile)
        drive, path = os.path.splitdrive(userprofile)
        if drive:
            env.setdefault("HOMEDRIVE", drive)
        if path:
            env.setdefault("HOMEPATH", path)
    env.pop("CODEX_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    return env


def _diagnostic_environment(codex_home: Path) -> dict[str, object]:
    env = _runner_environment(codex_home)
    diagnostics = {}
    for key in (
        "CODEX_HOME",
        "OMA7_EPHEMERAL_CODEX_HOME",
        "APPDATA",
        "LOCALAPPDATA",
        "SystemRoot",
        "ComSpec",
        "PATH",
        "PATHEXT",
        "USERPROFILE",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "TEMP",
        "TMP",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ):
        if key in env:
            diagnostics[key] = env[key]
    diagnostics["redacted_secret_key_count"] = sum(
        1
        for key in env
        if key.upper().endswith(("_KEY", "_TOKEN", "_SECRET"))
        or "PASSWORD" in key.upper()
        or "CREDENTIAL" in key.upper()
        or "AUTH" in key.upper()
    )
    return diagnostics


def _normalized_path(path: str | None) -> str | None:
    if path is None:
        return None
    return os.path.normcase(os.path.normpath(path))


def _load_first_real_mission_prompt() -> str:
    mission_doc = ROOT / "docs" / "agent" / "FIRST-REAL-MISSION.md"
    if mission_doc.exists():
        return mission_doc.read_text(encoding="utf-8")
    return "Execute the repository self-hosted first real G0 mission."


def _json_summary(**payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _emit_failure(**payload: object) -> int:
    print(_json_summary(**payload))
    return 1


def _run_real_codex(codex_path: str, codex_home: Path, prompt: str, environment: dict[str, str]) -> tuple[int, str, str, str]:
    result = run_codex_command(
        codex_path,
        ["exec"],
        code_home=str(codex_home),
        environment=environment,
        cwd=str(ROOT),
        stdin=prompt,
    )
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    return result.returncode, stdout, stderr, "codex exec"


def _run_host_preflight_auth_probe(codex_home: Path, environment: dict[str, str]) -> object:
    return run_host_codex_preflight_probe(
        preflight_script=str(ROOT / "scripts" / "host-codex-preflight.ps1"),
        code_home=str(codex_home),
        environment=environment,
        cwd=str(ROOT),
    )


def _codex_version(codex_path: str, codex_home: Path, environment: dict[str, str]) -> tuple[int, str, str]:
    result = run_codex_command(
        codex_path,
        ["--version"],
        code_home=str(codex_home),
        environment=environment,
        cwd=str(ROOT),
    )
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    return result.returncode, stdout, stderr


def _determine_g0_eligibility(environment: dict[str, str]) -> bool:
    audit_path = ROOT / "scripts" / "real-implementation-audit.py"
    result = run_codex_command(sys.executable, [str(audit_path)], environment=environment, cwd=str(ROOT))
    if result.returncode != 0:
        return False
    try:
        payload = json.loads((result.stdout or "").strip())
    except json.JSONDecodeError:
        return False
    for item in payload.get("paused_fronts", []):
        if item.get("title", "").lower() == "first real g0":
            return False
    return True


def main() -> int:
    codex_home = _resolve_ephemeral_codex_home()
    if codex_home is None:
        return _emit_failure(
            stage="codex_home_probe",
            reason="ephemeral CODEX_HOME unavailable",
            runner_environment=_diagnostic_environment(Path(tempfile.gettempdir()) / "oma7-ephemeral-codex-home"),
        )
    codex_home.mkdir(parents=True, exist_ok=True)
    runner_environment = _runner_environment(codex_home)
    codex_path = codex_executable()
    if codex_path is None:
        return _emit_failure(
            stage="codex_cli_probe",
            reason="codex executable unavailable",
            code_home=str(codex_home),
            runner_environment=_diagnostic_environment(codex_home),
        )

    auth_probe = _run_host_preflight_auth_probe(codex_home, runner_environment)
    auth_status = auth_probe.facts.get("CODEX_AUTH_STATUS")
    cli_capability = auth_probe.facts.get("CODEX_CLI_CAPABILITY")
    preflight_codex_path = auth_probe.facts.get("HOST_CODEX_CLI_PATH") or auth_probe.facts.get("CODEX_CLI_EXE")
    if (
        auth_probe.returncode != 0
        or auth_status != "AUTH_READY"
        or cli_capability != "CLI_AVAILABLE"
        or preflight_codex_path is None
        or _normalized_path(preflight_codex_path) != _normalized_path(codex_path)
    ):
        return _emit_failure(
            stage="auth_probe",
            codex_path=codex_path,
            code_home=str(codex_home),
            preflight_exit_code=auth_probe.returncode,
            preflight_stdout=auth_probe.stdout,
            preflight_stderr=auth_probe.stderr,
            preflight_command=list(auth_probe.command),
            preflight_facts=auth_probe.facts,
            cli_capability=cli_capability or "CLI_ABSENT",
            auth_status=auth_status or "NOT_READY",
            login_status_output=auth_probe.facts.get("EPHEMERAL_CODEX_LOGIN_STATUS"),
            reason=auth_probe.facts.get("CODEX_CLI_REASON") or auth_probe.stderr or auth_probe.stdout or "auth probe unavailable",
            runner_environment=_diagnostic_environment(codex_home),
        )

    version_exit, version_stdout, version_stderr = _codex_version(codex_path, codex_home, runner_environment)
    if version_exit != 0 or not version_stdout:
        return _emit_failure(
            stage="codex_version_probe",
            codex_path=codex_path,
            code_home=str(codex_home),
            stdout=version_stdout,
            stderr=version_stderr,
            runner_environment=_diagnostic_environment(codex_home),
        )

    spec = build_first_real_mission_spec(ROOT, DEFAULT_RUNTIME_PINS)
    attempt = new_attempt_identity(
        spec.mission_identity.identity(),
        1,
        subject_identity=spec.subject_identity,
        execution_context_identity=spec.execution_context_identity,
    )

    prompt = _load_first_real_mission_prompt()
    codex_exit, codex_stdout, codex_stderr, codex_command = _run_real_codex(codex_path, codex_home, prompt, runner_environment)
    if codex_exit != 0:
        return _emit_failure(
            stage="codex_exec",
            codex_path=codex_path,
            code_home=str(codex_home),
            command=codex_command,
            exit_code=codex_exit,
            stdout=codex_stdout,
            stderr=codex_stderr,
            runner_environment=_diagnostic_environment(codex_home),
            attempt_id=attempt.attempt_id,
            run_id=attempt.run_id,
        )

    evidence_root = ROOT / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    execution_facts = {
        "run_id": attempt.run_id,
        "attempt_id": attempt.attempt_id,
        "evidence_root": str(evidence_root),
        "codex_binary_digest": spec.execution_context_identity.codex_binary_digest,
        "codex_version": spec.execution_context_identity.codex_version,
        "model": spec.execution_context_identity.model,
        "reasoning_level": spec.execution_context_identity.reasoning_level,
        "harness_commit_or_digest": spec.execution_context_identity.harness_commit_or_digest,
        "harness_configuration_digest": spec.execution_context_identity.harness_configuration_digest,
        "dataset_revision": spec.execution_context_identity.dataset_revision,
        "dependency_lock_digest": spec.execution_context_identity.dependency_lock_digest,
        "environment_container_image_digest": spec.execution_context_identity.environment_container_image_digest,
        "toolchain_identity": spec.execution_context_identity.toolchain_identity,
    }
    verification_facts = {
        "run_id": attempt.run_id,
        "attempt_id": attempt.attempt_id,
        "dataset_revision": spec.verification_context_identity.dataset_revision,
        "oracle_test_patch_identity": spec.verification_context_identity.oracle_test_patch_identity,
        "harness_commit_or_digest": spec.verification_context_identity.harness_commit_or_digest,
        "verification_configuration_digest": spec.verification_context_identity.verification_configuration_digest,
        "verifier_identity": spec.verification_context_identity.verifier_identity,
    }

    capture = ReleaseCandidateExecutionCapture(
        attempt_identity=attempt,
        mission_identity=spec.mission_identity,
        subject_identity=spec.subject_identity,
        materialization_identity=spec.materialization_identity,
        execution_context_identity=spec.execution_context_identity,
        verification_context_identity=spec.verification_context_identity,
        scope_policy_identity=spec.scope_policy_identity,
        predicate={"kind": REAL_EXECUTION_PREDICATE_KIND},
        execution_facts=execution_facts,
        verification_facts=verification_facts,
        verifier_id=spec.verification_context_identity.verifier_identity,
    )

    try:
        _ = build_release_candidate_execution_evidence(capture)
    except Exception as exc:
        return _emit_failure(
            stage="release_candidate_evidence_validation",
            error=str(exc),
            codex_path=codex_path,
            code_home=str(codex_home),
            attempt_id=attempt.attempt_id,
            run_id=attempt.run_id,
        )

    artifacts = persist_release_candidate_execution_artifacts(capture=capture)
    g0_eligible = _determine_g0_eligibility(runner_environment)

    print(
        _json_summary(
            attempt_id=attempt.attempt_id,
            run_id=attempt.run_id,
            code_home=str(codex_home),
            codex_path=codex_path,
            codex_version_stdout=version_stdout,
            codex_exec_exit_code=codex_exit,
            e3_pass=True,
            g0_eligible=g0_eligible,
            evidence_path=artifacts.evidence_path,
            accounting_head=artifacts.accounting_head,
            accounting_event_count=artifacts.accounting_event_count,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
