from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.codex_runtime import CodexAuthStatus, CodexCliCapability, probe_codex_runtime


class CodexRuntimeTests(unittest.TestCase):
    def test_cli_absent_skips_login_status_probe(self) -> None:
        with patch("oma7.codex_runtime.codex_executable", return_value=None), patch(
            "oma7.codex_runtime.codex_login_status"
        ) as login_mock:
            status = probe_codex_runtime()
        self.assertEqual(status.cli_capability, CodexCliCapability.CLI_ABSENT)
        self.assertEqual(status.auth_status, CodexAuthStatus.NOT_PROBED)
        self.assertFalse(status.cli_available)
        self.assertFalse(status.auth_ready)
        login_mock.assert_not_called()

    def test_cli_available_not_ready_reports_auth_not_ready(self) -> None:
        with patch("oma7.codex_runtime.codex_executable", return_value=r"C:\codex.exe"), patch(
            "oma7.codex_runtime.codex_login_status", return_value=(False, "not logged in")
        ) as login_mock:
            status = probe_codex_runtime(code_home=r"C:\Users\Igor\AppData\Local\Temp\oma7")
        self.assertEqual(status.cli_capability, CodexCliCapability.CLI_AVAILABLE)
        self.assertEqual(status.auth_status, CodexAuthStatus.NOT_READY)
        self.assertTrue(status.cli_available)
        self.assertFalse(status.auth_ready)
        self.assertEqual(status.executable, r"C:\codex.exe")
        self.assertEqual(status.login_status_output, "not logged in")
        login_mock.assert_called_once_with(r"C:\codex.exe", code_home=r"C:\Users\Igor\AppData\Local\Temp\oma7")

    def test_cli_available_ready_reports_auth_ready(self) -> None:
        with patch("oma7.codex_runtime.codex_executable", return_value=r"C:\codex.exe"), patch(
            "oma7.codex_runtime.codex_login_status", return_value=(True, "logged in")
        ):
            status = probe_codex_runtime()
        self.assertEqual(status.cli_capability, CodexCliCapability.CLI_AVAILABLE)
        self.assertEqual(status.auth_status, CodexAuthStatus.READY)
        self.assertTrue(status.auth_ready)


if __name__ == "__main__":
    unittest.main()
