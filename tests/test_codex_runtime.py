from __future__ import annotations

import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.codex_runtime import (
    CodexAuthStatus,
    CodexCliCapability,
    build_codex_environment,
    probe_codex_runtime,
    resolve_ephemeral_codex_home,
    run_host_codex_preflight_probe,
    run_codex_command,
)


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
        login_mock.assert_called_once_with(
            r"C:\codex.exe",
            code_home=r"C:\Users\Igor\AppData\Local\Temp\oma7",
            environment=None,
            cwd=None,
        )

    def test_cli_available_ready_reports_auth_ready(self) -> None:
        with patch("oma7.codex_runtime.codex_executable", return_value=r"C:\codex.exe"), patch(
            "oma7.codex_runtime.codex_login_status", return_value=(True, "logged in")
        ):
            status = probe_codex_runtime()
        self.assertEqual(status.cli_capability, CodexCliCapability.CLI_AVAILABLE)
        self.assertEqual(status.auth_status, CodexAuthStatus.READY)
        self.assertTrue(status.auth_ready)

    def test_windows_cmd_shim_uses_cmd_exe_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("oma7.codex_runtime.sys.platform", "win32"), patch(
            "oma7.codex_runtime.subprocess.run"
        ) as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "logged in"
            run.return_value.stderr = ""
            status = probe_codex_runtime(
                explicit_codex=r"C:\Users\Igor B\AppData\Roaming\npm\codex.cmd",
                code_home=str(Path(tmp) / "home"),
                cwd=str(Path(ROOT)),
            )
        self.assertEqual(status.cli_capability, CodexCliCapability.CLI_AVAILABLE)
        self.assertEqual(status.auth_status, CodexAuthStatus.READY)
        command = run.call_args[0][0]
        self.assertEqual([part.lower() if index == 0 else part for index, part in enumerate(command)], [
            r"c:\windows\system32\cmd.exe",
            "/d",
            "/s",
            "/c",
            '""C:\\Users\\Igor B\\AppData\\Roaming\\npm\\codex.cmd" login status"',
        ])

    def test_codex_environment_reuses_ephemeral_home_and_strips_api_key(self) -> None:
        env = build_codex_environment(
            code_home=r"C:\Users\Igor B\AppData\Local\Temp\oma7-ephemeral-codex-home",
            environment={
                "CODEX_API_KEY": "sk-test",
                "OPENAI_API_KEY": "sk-openai",
                "OTHER": "value",
            },
        )
        self.assertEqual(env["CODEX_HOME"], r"C:\Users\Igor B\AppData\Local\Temp\oma7-ephemeral-codex-home")
        self.assertEqual(env["OMA7_EPHEMERAL_CODEX_HOME"], r"C:\Users\Igor B\AppData\Local\Temp\oma7-ephemeral-codex-home")
        self.assertEqual(env["OTHER"], "value")
        self.assertNotIn("CODEX_API_KEY", env)
        self.assertNotIn("OPENAI_API_KEY", env)

    def test_codex_environment_mirrors_code_home_when_only_code_home_is_present(self) -> None:
        env = build_codex_environment(
            environment={
                "CODEX_HOME": r"C:\Users\Igor B\AppData\Local\Temp\oma7-ephemeral-codex-home",
                "OTHER": "value",
            },
        )
        self.assertEqual(env["CODEX_HOME"], r"C:\Users\Igor B\AppData\Local\Temp\oma7-ephemeral-codex-home")
        self.assertEqual(env["OMA7_EPHEMERAL_CODEX_HOME"], r"C:\Users\Igor B\AppData\Local\Temp\oma7-ephemeral-codex-home")
        self.assertEqual(env["OTHER"], "value")

    def test_resolve_ephemeral_codex_home_prefers_existing_temp_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "oma7-ephemeral-codex-home"
            codex_home.mkdir(parents=True)
            home = resolve_ephemeral_codex_home(
                environment={
                    "TEMP": str(Path(tmp)),
                    "TMP": str(Path(tmp) / "ignored"),
                },
            )
        self.assertEqual(home, str(codex_home.resolve()))

    def test_resolve_ephemeral_codex_home_accepts_existing_short_path_alias(self) -> None:
        short_home = r"C:\Users\IGORB~1\AppData\Local\Temp\oma7-ephemeral-codex-home"
        long_home = Path(r"C:\Users\Igor B\AppData\Local\Temp\oma7-ephemeral-codex-home")

        def fake_resolve(self: Path, strict: bool = False) -> Path:
            if str(self) == short_home:
                return long_home
            return Path(str(self))

        with patch("oma7.codex_runtime.Path.exists", return_value=True), patch(
            "oma7.codex_runtime.Path.is_dir", return_value=True
        ), patch("oma7.codex_runtime.Path.resolve", fake_resolve):
            home = resolve_ephemeral_codex_home(
                environment={
                    "OMA7_EPHEMERAL_CODEX_HOME": short_home,
                    "CODEX_HOME": short_home,
                }
            )
        self.assertEqual(home, str(long_home))

    def test_resolve_ephemeral_codex_home_fails_closed_when_home_missing(self) -> None:
        with patch("oma7.codex_runtime.Path.exists", return_value=False), patch(
            "oma7.codex_runtime.Path.is_dir", return_value=False
        ):
            home = resolve_ephemeral_codex_home(
                environment={
                    "CODEX_HOME": r"C:\missing\oma7-ephemeral-codex-home",
                    "TEMP": r"C:\missing\temp",
                    "TMP": r"C:\missing\tmp",
                }
            )
        self.assertIsNone(home)

    def test_run_codex_command_uses_same_ephemeral_home_for_cmd_shim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("oma7.codex_runtime.sys.platform", "win32"), patch(
            "oma7.codex_runtime.subprocess.run"
        ) as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "codex-cli 0.149.0"
            run.return_value.stderr = ""
            run_codex_command(
                r"C:\Users\Igor B\AppData\Roaming\npm\codex.cmd",
                ["exec"],
                code_home=str(Path(tmp) / "oma7-ephemeral-codex-home"),
                environment={
                    "CODEX_API_KEY": "sk-test",
                    "OPENAI_API_KEY": "sk-openai",
                },
                cwd=str(ROOT),
                stdin="hello",
            )
            command = run.call_args[0][0]
            environment = run.call_args.kwargs["env"]
            self.assertEqual([part.lower() if index == 0 else part for index, part in enumerate(command)], [
                r"c:\windows\system32\cmd.exe",
                "/d",
                "/s",
                "/c",
                '""C:\\Users\\Igor B\\AppData\\Roaming\\npm\\codex.cmd" exec"',
            ])
            self.assertEqual(run.call_args.kwargs["cwd"], str(ROOT))
            self.assertEqual(environment["CODEX_HOME"], str(Path(tmp) / "oma7-ephemeral-codex-home"))
            self.assertEqual(environment["OMA7_EPHEMERAL_CODEX_HOME"], str(Path(tmp) / "oma7-ephemeral-codex-home"))
            self.assertNotIn("CODEX_API_KEY", environment)
            self.assertNotIn("OPENAI_API_KEY", environment)

    def test_host_preflight_probe_parses_ready_auth_and_preserves_code_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("oma7.codex_runtime.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "\n".join(
                [
                    "CODEX_CLI_CAPABILITY=CLI_AVAILABLE",
                    "CODEX_AUTH_STATUS=AUTH_READY",
                    "CODEX_AUTH_READY=True",
                    r"HOST_CODEX_CLI_PATH=C:\Users\Igor B\AppData\Roaming\npm\codex.cmd",
                    r"HOST_CODEX_CLI_SOURCE=installed:C:\Users\Igor B\AppData\Roaming\npm\codex.cmd",
                    "EPHEMERAL_CODEX_LOGIN_STATUS=AUTH_READY: Logged in using ChatGPT",
                ]
            )
            run.return_value.stderr = ""
            probe = run_host_codex_preflight_probe(
                preflight_script=r"C:\Projetos\OMA7\oma-experiment\scripts\host-codex-preflight.ps1",
                code_home=str(Path(tmp) / "oma7-ephemeral-codex-home"),
                environment={
                    "CODEX_API_KEY": "sk-test",
                    "OPENAI_API_KEY": "sk-openai",
                    "OTHER": "value",
                },
                cwd=str(ROOT),
                powershell=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            )
        self.assertEqual(probe.returncode, 0)
        self.assertEqual(probe.auth_status, CodexAuthStatus.READY)
        self.assertEqual(probe.cli_capability, CodexCliCapability.CLI_AVAILABLE)
        self.assertTrue(probe.auth_ready)
        self.assertEqual(probe.code_home, str(Path(tmp) / "oma7-ephemeral-codex-home"))
        self.assertEqual(probe.cwd, str(ROOT))
        self.assertEqual(
            probe.facts["EPHEMERAL_CODEX_LOGIN_STATUS"],
            "AUTH_READY: Logged in using ChatGPT",
        )
        self.assertEqual(run.call_args.kwargs["cwd"], str(ROOT))
        self.assertEqual(run.call_args.kwargs["env"]["CODEX_HOME"], str(Path(tmp) / "oma7-ephemeral-codex-home"))
        self.assertNotIn("CODEX_API_KEY", run.call_args.kwargs["env"])
        self.assertNotIn("OPENAI_API_KEY", run.call_args.kwargs["env"])

    def test_host_preflight_probe_treats_ambiguous_output_as_incomplete(self) -> None:
        with patch("oma7.codex_runtime.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "unexpected output"
            run.return_value.stderr = ""
            probe = run_host_codex_preflight_probe(
                preflight_script=r"C:\Projetos\OMA7\oma-experiment\scripts\host-codex-preflight.ps1",
                code_home=r"C:\Users\IGORB~1\AppData\Local\Temp\oma7-ephemeral-codex-home",
                environment={"CODEX_HOME": r"C:\Users\IGORB~1\AppData\Local\Temp\oma7-ephemeral-codex-home"},
                cwd=str(ROOT),
            )
        self.assertEqual(probe.returncode, 0)
        self.assertIsNone(probe.cli_capability)
        self.assertIsNone(probe.auth_status)
        self.assertFalse(probe.auth_ready)
        self.assertEqual(probe.facts, {})


if __name__ == "__main__":
    unittest.main()
