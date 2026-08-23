from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.preflight import PreflightResult, RuntimePins, SandboxPreflightConfig, run_sandbox_preflight


class SandboxPreflightTests(unittest.TestCase):
    def runtime_pins(self) -> RuntimePins:
        return RuntimePins(
            codex_sha256="6ee176b43f96b2294c8e2265d599f829e161b2c2ad34cb2b8fbf5f836fd34b8c",
            codex_version="0.1.0",
            model="o-model",
            reasoning_level="high",
            harness_commit_or_digest="8be9acebf1387b0fe0abdfdce8bb2ef9a2c0ac50",
            harness_configuration_digest="sha256:1111111111111111111111111111111111111111111111111111111111111111",
            dataset_revision="sha256:2222222222222222222222222222222222222222222222222222222222222222",
            dependency_lock_digest="sha256:3333333333333333333333333333333333333333333333333333333333333333",
            container_image_digest="sha256:4444444444444444444444444444444444444444444444444444444444444444",
            toolchain_identity="sha256:5555555555555555555555555555555555555555555555555555555555555555",
        )

    def test_sandbox_preflight_emits_canonical_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=workspace,
                    pins=self.runtime_pins(),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=True,
                    codex_home=Path(tmp) / "oma7-ephemeral-codex-home",
                    command=("python", "-m", "unittest", "discover", "-s", "tests", "-v"),
                    workdir="/workspace",
                    network="none",
                    mounts=((workspace, "/workspace", "rw"),),
                    environment=("CODEX_HOME=/codex-home",),
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
            self.assertIn("network access succeeded", result.failure_reasons)
            self.assertTrue(result.execution_context_id)
            self.assertIn("python", result.command[0])
            self.assertEqual(result.codex_home.endswith("oma7-ephemeral-codex-home"), True)
            self.assertEqual(result.network, "none")
            self.assertEqual(result.mounts, ((str(workspace), "/workspace", "rw"),))
            self.assertIn("CODEX_HOME=/codex-home", result.environment)

    def test_sandbox_preflight_blocks_invalid_command_and_mounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=workspace,
                    pins=self.runtime_pins(),
                    approval_noninteractive=False,
                    automatic_escalation_disabled=False,
                    codex_home=Path(tmp) / "oma7-ephemeral-codex-home",
                    command=(),
                    workdir="workspace",
                    network="",
                    mounts=((Path("relative"), "workspace", "bad"),),
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
            self.assertIn("sandbox command missing", result.failure_reasons)
            self.assertIn("workdir is not absolute", result.failure_reasons)
            self.assertIn("network policy missing", result.failure_reasons)
            self.assertIn("host path is not absolute", " ".join(result.failure_reasons))


if __name__ == "__main__":
    unittest.main()
