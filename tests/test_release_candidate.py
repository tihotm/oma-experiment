from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.preflight import DEFAULT_RUNTIME_PINS
from oma7.release_candidate import (
    build_default_release_candidate_readiness,
    build_first_real_mission_spec,
    build_release_candidate_plan,
)


class ReleaseCandidateTests(unittest.TestCase):
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
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "oma7-release-candidate-readiness.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("CODEX_CLI_CAPABILITY=CLI_ABSENT", result.stdout)
        self.assertIn("CODEX_AUTH_STATUS=NOT_PROBED", result.stdout)
        self.assertIn("RC_ATTEMPT_CREATED=False", result.stdout)
        self.assertIn("RC_REAL_CODEX_EXEC=0", result.stdout)
        self.assertIn("RC_MISSION_PLAN_READY=True", result.stdout)
        self.assertIn("RC_SANDBOX_PREFLIGHT=ENVIRONMENT_BLOCKED", result.stdout)
        self.assertIn("CODEX_AUTH_READY=False", result.stdout)

    def test_release_candidate_readiness_script_emits_json(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "oma7-release-candidate-readiness.py"), "--json"],
            cwd=ROOT,
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
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "oma7-release-candidate-readiness.py"), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn('"codex_cli_capability": "cli_absent"', result.stdout.lower())
        self.assertIn('"codex_auth_status": "not_probed"', result.stdout.lower())

    def test_release_candidate_readiness_emits_sandbox_facts(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "oma7-release-candidate-readiness.py"), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn('"sandbox_code_home":', result.stdout.lower())
        self.assertIn('"sandbox_command":', result.stdout.lower())
        self.assertIn('"sandbox_network": "none"', result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
