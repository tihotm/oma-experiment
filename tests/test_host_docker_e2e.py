from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import host_docker_e2e


class HostDockerE2ETests(unittest.TestCase):
    def test_control_record_helper_builds_canonical_identity(self) -> None:
        budget = host_docker_e2e.RetryBudget(2, 30, 10)
        record = host_docker_e2e._control_record("run-test", budget)
        self.assertEqual(record.run_id, "run-test")
        self.assertEqual(record.budget, budget)
        self.assertTrue(record.mission_identity.is_valid())

    def test_case_e_probe_uses_codex_version_without_shell(self) -> None:
        captured: dict[str, list[str] | str] = {}

        def fake_run(docker: str, args, *, input_text=None):
            captured["docker"] = docker
            captured["args"] = list(args)
            return host_docker_e2e.subprocess.CompletedProcess(args=[docker, *args], returncode=0, stdout="codex-cli 0.test\n", stderr="")

        with patch("host_docker_e2e._run", side_effect=fake_run):
            result = host_docker_e2e._run_docker_probe("docker")

        self.assertTrue(result.passed)
        self.assertEqual(captured["args"], ["run", "--rm", host_docker_e2e.PINNED_IMAGE, "codex", "--version"])
        self.assertNotIn("sh", captured["args"])

    def test_successful_host_docker_e2e_marks_synthetic_evidence_blocked(self) -> None:
        summary = {
            "HOST_DOCKER_STAGE_REGISTRY": "CASE_E,OFFLINE_CONTROL_PLANE",
            "HOST_DOCKER_STAGES": 18,
            "RUNTIME_REPEATABILITY_RUNS": 3,
        }
        with patch("host_docker_e2e._emit") as emit:
            host_docker_e2e._publish_canonical_execution_artifacts(summary)
        emit.assert_any_call("CANONICAL_EVIDENCE_PUBLISHED", False)
        emit.assert_any_call("CANONICAL_PUBLISH_BLOCKER", "host_docker_e2e is not product execution evidence")


if __name__ == "__main__":
    unittest.main()
