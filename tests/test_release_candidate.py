from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.preflight import DEFAULT_RUNTIME_PINS
from oma7.release_candidate import (
    build_default_release_candidate_readiness,
    build_first_real_mission_spec,
    build_release_candidate_execution_evidence,
    build_release_candidate_plan,
    persist_release_candidate_execution_artifacts,
    ReleaseCandidateExecutionCapture,
)
from oma7.control_plane import new_attempt_identity


class ReleaseCandidateTests(unittest.TestCase):
    def _load_release_candidate_runner(self):
        runner_path = ROOT / "scripts" / "oma7-release-candidate-run.py"
        spec = importlib.util.spec_from_file_location("oma7_release_candidate_run", runner_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module

    def _write_fake_codex_cmd(self, tmp: str) -> dict[str, str]:
        appdata = Path(tmp) / "App Data" / "Roaming"
        npm_dir = appdata / "npm"
        npm_dir.mkdir(parents=True)
        codex_cmd = npm_dir / "codex.cmd"
        codex_cmd.write_text(
            "@echo off\r\n"
            "if /I \"%~1\"==\"--version\" goto version\r\n"
            "exit /b 1\r\n"
            ":version\r\n"
            "echo codex-cli 0.test\r\n"
            "exit /b 0\r\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["APPDATA"] = str(appdata)
        env["LOCALAPPDATA"] = str(Path(tmp) / "App Data" / "Local")
        env["OMA7_EPHEMERAL_CODEX_HOME"] = str(Path(tmp) / "codex-home")
        env.pop("CODEX_HOME", None)
        env.pop("OMA7_CODEX_CLI_PATH", None)
        env.pop("CODEX_CLI_PATH", None)
        env.pop("CODEX_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
        return env

    def test_first_real_mission_spec_is_canonic(self) -> None:
        spec = build_first_real_mission_spec(ROOT, DEFAULT_RUNTIME_PINS)
        self.assertTrue(spec.mission_identity.is_valid())
        self.assertTrue(spec.execution_context_identity.is_valid())
        self.assertEqual(spec.harness_binding_identity, "oma7-harness:release-candidate")
        self.assertEqual(spec.retry_budget.max_attempts, 1)
        self.assertEqual(spec.verification_context_identity.verifier_identity, "oma7-first-real-g0-verifier")

    def test_release_candidate_plan_is_ready_without_attempt(self) -> None:
        spec = build_first_real_mission_spec(ROOT, DEFAULT_RUNTIME_PINS)
        plan = build_release_candidate_plan(spec)
        self.assertEqual(plan.execution_context_id, spec.execution_context_identity.identity())
        self.assertEqual(plan.blocked_reasons, ())
        self.assertEqual(plan.result.value, "READY")

    def test_release_candidate_readiness_script_emits_rehearsal_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = self._write_fake_codex_cmd(tmp)
            env["OMA7_DISABLE_READINESS_SUITE_SUMMARY"] = "1"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "oma7-release-candidate-readiness.py")],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("CODEX_CLI_CAPABILITY=CLI_AVAILABLE", result.stdout)
        self.assertIn("CODEX_AUTH_STATUS=NOT_PROBED", result.stdout)
        self.assertIn("RC_ATTEMPT_CREATED=False", result.stdout)
        self.assertIn("RC_REAL_CODEX_EXEC=0", result.stdout)
        self.assertIn("RC_MISSION_PLAN_READY=True", result.stdout)
        self.assertIn("RC_SANDBOX_PREFLIGHT=ENVIRONMENT_BLOCKED", result.stdout)
        self.assertIn("CODEX_AUTH_READY=False", result.stdout)

    def test_release_candidate_readiness_script_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = self._write_fake_codex_cmd(tmp)
            env["OMA7_DISABLE_READINESS_SUITE_SUMMARY"] = "1"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "oma7-release-candidate-readiness.py"), "--json"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn('"auth_ready": false', result.stdout.lower())
        self.assertIn('"mission_plan_ready": true', result.stdout.lower())
        self.assertIn('"sandbox_preflight": "environment_blocked"', result.stdout.lower())
        self.assertIn('"real_codex_exec": 0', result.stdout.lower())

    def test_release_candidate_readiness_distinguishes_codex_cli_absence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = self._write_fake_codex_cmd(tmp)
            env["OMA7_DISABLE_READINESS_SUITE_SUMMARY"] = "1"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "oma7-release-candidate-readiness.py"), "--json"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["codex_cli_capability"], "CLI_AVAILABLE")
        self.assertEqual(payload["codex_auth_status"], "NOT_PROBED")
        self.assertTrue(payload["codex_cli_path"].lower().endswith(r"\npm\codex.cmd"))

    def test_release_candidate_readiness_emits_sandbox_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = self._write_fake_codex_cmd(tmp)
            env["OMA7_DISABLE_READINESS_SUITE_SUMMARY"] = "1"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "oma7-release-candidate-readiness.py"), "--json"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn('"sandbox_code_home":', result.stdout.lower())
        self.assertIn('"sandbox_command":', result.stdout.lower())
        self.assertIn('"sandbox_network": "none"', result.stdout.lower())

    def test_release_candidate_execution_evidence_rejects_synthetic_host_e2e_kind(self) -> None:
        capture = self._real_execution_capture(ROOT)
        with self.assertRaises(ValueError):
            build_release_candidate_execution_evidence(replace(capture, predicate={"kind": "host_docker_e2e"}))

    def test_release_candidate_execution_evidence_rejects_missing_factual_fields(self) -> None:
        capture = self._real_execution_capture(ROOT)
        broken = replace(capture, execution_facts={k: v for k, v in capture.execution_facts.items() if k != "codex_version"})
        with self.assertRaises(ValueError):
            build_release_candidate_execution_evidence(broken)

    def test_release_candidate_execution_artifacts_require_factual_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            capture = self._real_execution_capture(ROOT, Path(tmp))
            artifacts = persist_release_candidate_execution_artifacts(capture=capture, accounting_cost_units=2)
            self.assertEqual(artifacts.evidence.run_id, capture.attempt_identity.run_id)
            self.assertEqual(artifacts.accounting_head is not None, True)

    def _real_execution_capture(self, workspace: Path, evidence_root: Path | None = None) -> ReleaseCandidateExecutionCapture:
        spec = build_first_real_mission_spec(workspace, DEFAULT_RUNTIME_PINS)
        attempt = new_attempt_identity(
            spec.mission_identity.identity(),
            1,
            subject_identity=spec.subject_identity,
            execution_context_identity=spec.execution_context_identity,
        )
        evidence_root = evidence_root or (workspace / "evidence")
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
        return ReleaseCandidateExecutionCapture(
            attempt_identity=attempt,
            mission_identity=spec.mission_identity,
            subject_identity=spec.subject_identity,
            materialization_identity=spec.materialization_identity,
            execution_context_identity=spec.execution_context_identity,
            verification_context_identity=spec.verification_context_identity,
            scope_policy_identity=spec.scope_policy_identity,
            predicate={"kind": "real-execution"},
            execution_facts=execution_facts,
            verification_facts=verification_facts,
            verifier_id=spec.verification_context_identity.verifier_identity,
        )

    def test_host_preflight_debug_switch_emits_codex_detection_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = self._write_fake_codex_cmd(tmp)
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT / "scripts" / "host-codex-preflight.ps1"),
                    "-DebugCodexCliDetection",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertNotIn("FormatError", result.stdout + result.stderr)
        self.assertIn("DEBUG_APPDATA=", result.stdout)
        self.assertIn("DEBUG_LOCALAPPDATA=", result.stdout)
        self.assertIn("DEBUG_STANDARD_CANDIDATES=", result.stdout)
        self.assertIn("DEBUG_CANDIDATE_RESULT=", result.stdout)
        self.assertIn("DEBUG_PROBE_EXIT=", result.stdout)
        self.assertIn("DEBUG_PROBE_STDOUT=", result.stdout)
        self.assertIn("DEBUG_PROBE_STDERR=", result.stdout)
        self.assertIn("DEBUG_FINAL_CLI_PROBE=", result.stdout)
        self.assertIn("CODEX_CLI_CAPABILITY=", result.stdout)

    def test_release_candidate_runner_reuses_ephemeral_home_and_strips_api_key(self) -> None:
        module = self._load_release_candidate_runner()
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            old_env = {name: os.environ.get(name) for name in ("OMA7_EPHEMERAL_CODEX_HOME", "CODEX_HOME", "CODEX_API_KEY", "OPENAI_API_KEY")}
            auth_probe_environment = None
            try:
                os.environ["OMA7_EPHEMERAL_CODEX_HOME"] = str(codex_home)
                os.environ["CODEX_HOME"] = str(codex_home)
                os.environ["CODEX_API_KEY"] = "sk-test"
                os.environ["OPENAI_API_KEY"] = "sk-openai"
                env = module._runner_environment(codex_home)
            finally:
                for name, value in old_env.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value
        self.assertEqual(env["CODEX_HOME"], str(codex_home))
        self.assertEqual(env["OMA7_EPHEMERAL_CODEX_HOME"], str(codex_home))
        self.assertNotIn("CODEX_API_KEY", env)
        self.assertNotIn("OPENAI_API_KEY", env)

    def test_release_candidate_runner_redacts_sensitive_environment_in_diagnostics(self) -> None:
        module = self._load_release_candidate_runner()
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            old_env = {name: os.environ.get(name) for name in ("OMA7_EPHEMERAL_CODEX_HOME", "CODEX_HOME", "CODEX_API_KEY", "OPENAI_API_KEY", "SECRET_TOKEN")}
            try:
                os.environ["OMA7_EPHEMERAL_CODEX_HOME"] = str(codex_home)
                os.environ["CODEX_HOME"] = str(codex_home)
                os.environ["CODEX_API_KEY"] = "sk-test"
                os.environ["OPENAI_API_KEY"] = "sk-openai"
                os.environ["SECRET_TOKEN"] = "secret"
                diagnostics = module._diagnostic_environment(codex_home)
            finally:
                for name, value in old_env.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value
        serialized = str(diagnostics)
        self.assertIn("CODEX_HOME", diagnostics)
        self.assertIn("OMA7_EPHEMERAL_CODEX_HOME", diagnostics)
        self.assertNotIn("CODEX_API_KEY", serialized)
        self.assertNotIn("OPENAI_API_KEY", serialized)
        self.assertNotIn("SECRET_TOKEN", serialized)
        self.assertIn("redacted_secret_key_count", diagnostics)

    def test_release_candidate_runner_fails_closed_without_auth(self) -> None:
        module = self._load_release_candidate_runner()
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            with patch.object(module, "codex_executable", return_value=r"C:\Users\Igor B\AppData\Roaming\npm\codex.cmd"), patch.object(
                module,
                "run_host_codex_preflight_probe",
            ) as probe_mock, patch.object(module, "run_codex_command") as run_mock:
                probe_mock.return_value = SimpleNamespace(
                    returncode=0,
                    stdout="CODEX_CLI_CAPABILITY=CLI_AVAILABLE\nCODEX_AUTH_STATUS=AUTH_NOT_READY\nCODEX_AUTH_READY=False\nHOST_CODEX_CLI_PATH=C:\\Users\\Igor B\\AppData\\Roaming\\npm\\codex.cmd\nHOST_CODEX_CLI_SOURCE=installed:C:\\Users\\Igor B\\AppData\\Roaming\\npm\\codex.cmd\nEPHEMERAL_CODEX_LOGIN_STATUS=AUTH_NOT_READY: Not logged in",
                    stderr="",
                    command=("powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "host-codex-preflight.ps1")),
                    cwd=str(ROOT),
                    code_home=str(codex_home),
                    facts={
                        "CODEX_CLI_CAPABILITY": "CLI_AVAILABLE",
                        "CODEX_AUTH_STATUS": "AUTH_NOT_READY",
                        "CODEX_AUTH_READY": "False",
                        "HOST_CODEX_CLI_PATH": r"C:\Users\Igor B\AppData\Roaming\npm\codex.cmd",
                        "HOST_CODEX_CLI_SOURCE": r"installed:C:\Users\Igor B\AppData\Roaming\npm\codex.cmd",
                        "EPHEMERAL_CODEX_LOGIN_STATUS": "AUTH_NOT_READY: Not logged in",
                    },
                )
                old_env = os.environ.get("OMA7_EPHEMERAL_CODEX_HOME")
                try:
                    os.environ["OMA7_EPHEMERAL_CODEX_HOME"] = str(codex_home)
                    result = module.main()
                finally:
                    if old_env is None:
                        os.environ.pop("OMA7_EPHEMERAL_CODEX_HOME", None)
                    else:
                        os.environ["OMA7_EPHEMERAL_CODEX_HOME"] = old_env
        self.assertEqual(result, 1)
        run_mock.assert_not_called()

    def test_release_candidate_runner_requires_ephemeral_codex_home(self) -> None:
        module = self._load_release_candidate_runner()
        old_env = {name: os.environ.get(name) for name in ("OMA7_EPHEMERAL_CODEX_HOME", "CODEX_HOME")}
        try:
            os.environ.pop("OMA7_EPHEMERAL_CODEX_HOME", None)
            os.environ.pop("CODEX_HOME", None)
            result = module.main()
        finally:
            for name, value in old_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.assertEqual(result, 1)

    def test_release_candidate_runner_reuses_ready_auth_without_api_key(self) -> None:
        module = self._load_release_candidate_runner()
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            codex_home.mkdir(parents=True, exist_ok=True)
            fake_version = subprocess.CompletedProcess(
                args=["codex", "--version"],
                returncode=0,
                stdout="codex-cli 0.149.0",
                stderr="",
            )
            fake_exec = subprocess.CompletedProcess(
                args=["codex", "exec"],
                returncode=0,
                stdout="mission complete",
                stderr="",
            )
            fake_audit = subprocess.CompletedProcess(
                args=[sys.executable, str(ROOT / "scripts" / "real-implementation-audit.py")],
                returncode=0,
                stdout='{"paused_fronts":[]}',
                stderr="",
            )
            old_env = {name: os.environ.get(name) for name in ("OMA7_EPHEMERAL_CODEX_HOME", "CODEX_HOME", "CODEX_API_KEY", "OPENAI_API_KEY")}
            try:
                os.environ["OMA7_EPHEMERAL_CODEX_HOME"] = str(codex_home)
                os.environ["CODEX_HOME"] = str(codex_home)
                os.environ.pop("CODEX_API_KEY", None)
                os.environ.pop("OPENAI_API_KEY", None)
                with patch.object(module, "codex_executable", return_value=r"C:\Users\Igor B\AppData\Roaming\npm\codex.cmd"), patch.object(
                    module,
                    "run_host_codex_preflight_probe",
                    return_value=SimpleNamespace(
                        returncode=0,
                        stdout="CODEX_CLI_CAPABILITY=CLI_AVAILABLE\nCODEX_AUTH_STATUS=AUTH_READY\nCODEX_AUTH_READY=True\nHOST_CODEX_CLI_PATH=C:\\Users\\Igor B\\AppData\\Roaming\\npm\\codex.cmd\nHOST_CODEX_CLI_SOURCE=installed:C:\\Users\\Igor B\\AppData\\Roaming\\npm\\codex.cmd\nEPHEMERAL_CODEX_LOGIN_STATUS=AUTH_READY: Logged in using ChatGPT",
                        stderr="",
                        command=("powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "host-codex-preflight.ps1")),
                        cwd=str(ROOT),
                        code_home=str(codex_home),
                        facts={
                            "CODEX_CLI_CAPABILITY": "CLI_AVAILABLE",
                            "CODEX_AUTH_STATUS": "AUTH_READY",
                            "CODEX_AUTH_READY": "True",
                            "HOST_CODEX_CLI_PATH": r"C:\Users\Igor B\AppData\Roaming\npm\codex.cmd",
                            "HOST_CODEX_CLI_SOURCE": r"installed:C:\Users\Igor B\AppData\Roaming\npm\codex.cmd",
                            "EPHEMERAL_CODEX_LOGIN_STATUS": "AUTH_READY: Logged in using ChatGPT",
                        },
                    ),
                ) as probe_mock, patch.object(
                    module,
                    "run_codex_command",
                    side_effect=[fake_version, fake_exec, fake_audit],
                ) as run_mock, patch.object(
                    module,
                    "persist_release_candidate_execution_artifacts",
                    return_value=type(
                        "Artifacts",
                        (),
                        {
                            "evidence_path": str(codex_home / "evidence.json"),
                            "accounting_head": "head",
                            "accounting_event_count": 1,
                        },
                    )(),
                ):
                    result = module.main()
                    auth_probe_call = probe_mock.call_args
            finally:
                for name, value in old_env.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value
        self.assertEqual(result, 0)
        resolved_home = Path(auth_probe_call.kwargs["code_home"]).resolve()
        self.assertEqual(resolved_home, codex_home.resolve())
        self.assertEqual(auth_probe_call.kwargs["environment"], module._runner_environment(resolved_home))
        self.assertEqual(auth_probe_call.kwargs["cwd"], str(ROOT))
        self.assertEqual(run_mock.call_count, 3)
        self.assertEqual(Path(run_mock.call_args_list[0].kwargs["code_home"]).resolve(), resolved_home)
        self.assertEqual(run_mock.call_args_list[0].kwargs["cwd"], str(ROOT))
        self.assertEqual(Path(run_mock.call_args_list[1].kwargs["code_home"]).resolve(), resolved_home)
        self.assertEqual(run_mock.call_args_list[1].kwargs["cwd"], str(ROOT))
        self.assertEqual(run_mock.call_args_list[2].args[0], sys.executable)
        self.assertEqual(run_mock.call_args_list[2].kwargs["cwd"], str(ROOT))

    def test_release_candidate_runner_derives_home_from_userprofile(self) -> None:
        module = self._load_release_candidate_runner()
        old_env = {name: os.environ.get(name) for name in ("USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH", "SystemRoot", "WINDIR", "ComSpec")}
        try:
            os.environ["USERPROFILE"] = r"C:\Users\Igor B"
            os.environ.pop("HOME", None)
            os.environ.pop("HOMEDRIVE", None)
            os.environ.pop("HOMEPATH", None)
            os.environ.pop("SystemRoot", None)
            os.environ.pop("WINDIR", None)
            os.environ.pop("ComSpec", None)
            env = module._runner_environment(Path(r"C:\Users\IGORB~1\AppData\Local\Temp\oma7-ephemeral-codex-home"))
        finally:
            for name, value in old_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.assertEqual(env["HOME"], r"C:\Users\Igor B")
        self.assertEqual(env["HOMEDRIVE"], r"C:")
        self.assertEqual(env["HOMEPATH"], r"\Users\Igor B")
        self.assertEqual(env["SystemRoot"], r"C:\Windows")
        self.assertEqual(env["WINDIR"], r"C:\Windows")
        self.assertEqual(env["ComSpec"], r"C:\Windows\System32\cmd.exe")


if __name__ == "__main__":
    unittest.main()
