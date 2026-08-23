from __future__ import annotations

from unittest.mock import patch
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.docker_lifecycle import DockerCapability, docker_capability, docker_runtime_status


class DockerRuntimeStatusTests(unittest.TestCase):
    def test_reports_missing_executable(self) -> None:
        available, reason = docker_runtime_status(r"C:\does-not-exist\docker.exe")
        self.assertFalse(available)
        self.assertEqual(reason, "docker executable unavailable")

    def test_reports_permission_denied(self) -> None:
        with patch("oma7.docker_lifecycle.Path.exists", return_value=True), patch(
            "oma7.docker_lifecycle.docker_version", return_value=None
        ), patch("oma7.docker_lifecycle._run") as run_mock:
            run_mock.return_value = type("R", (), {"stderr": "permission denied while trying to connect to the docker API", "stdout": ""})()
            available, reason = docker_runtime_status(r"C:\docker.exe")
        self.assertFalse(available)
        self.assertEqual(reason, "docker daemon access denied for current process token")

    def test_reports_context_resolution_failure(self) -> None:
        with patch("oma7.docker_lifecycle.Path.exists", return_value=True), patch(
            "oma7.docker_lifecycle.docker_version", return_value=None
        ), patch("oma7.docker_lifecycle._run") as run_mock:
            run_mock.return_value = type("R", (), {"stderr": "context not found: desktop-linux", "stdout": ""})()
            available, reason = docker_runtime_status(r"C:\docker.exe")
        self.assertFalse(available)
        self.assertEqual(reason, "docker context resolution failed")

    def test_docker_capability_classifies_ready_and_missing_cli(self) -> None:
        with patch("oma7.docker_lifecycle.docker_executable", return_value=r"C:\\docker.exe"), patch(
            "oma7.docker_lifecycle.docker_runtime_status", return_value=(True, "docker daemon reachable")
        ), patch("oma7.docker_lifecycle.docker_context", return_value="desktop-linux"), patch(
            "oma7.docker_lifecycle.inspect_image", return_value=type("I", (), {"digest": "sha256:1"})()
        ):
            capability, reason = docker_capability()
        self.assertEqual(capability, DockerCapability.READY)
        self.assertEqual(reason, "desktop-linux")

        with patch("oma7.docker_lifecycle.docker_executable", side_effect=FileNotFoundError("missing")):
            capability, reason = docker_capability()
        self.assertEqual(capability, DockerCapability.CLI_ABSENT)
        self.assertEqual(reason, "docker executable unavailable")


if __name__ == "__main__":
    unittest.main()
