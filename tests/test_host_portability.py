from __future__ import annotations

import os
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.host_portability import (
    HostCapabilitySupport,
    _probe_candidate_executable,
    resolve_codex_cli_path,
    resolve_docker_cli_path,
    resolve_host_capability,
)


class HostPortabilityTests(unittest.TestCase):
    def test_explicit_paths_define_supported_host(self) -> None:
        probe = resolve_host_capability(
            explicit_codex_cli=r"C:\codex\codex.exe",
            explicit_docker_cli=r"C:\docker\docker.exe",
        )
        self.assertEqual(probe.support, HostCapabilitySupport.SUPPORTED)
        self.assertEqual(probe.codex_cli_path, r"C:\codex\codex.exe")
        self.assertEqual(probe.docker_cli_path, r"C:\docker\docker.exe")
        self.assertEqual(probe.blockers, ())

    def test_missing_paths_fail_closed(self) -> None:
        old_env = {name: os.environ.get(name) for name in ("OMA7_CODEX_CLI_PATH", "CODEX_CLI_PATH", "OMA7_DOCKER_CLI_PATH", "DOCKER_CLI_PATH")}
        try:
            for name in old_env:
                os.environ.pop(name, None)
            with patch("oma7.host_portability.Path.exists", return_value=False):
                codex_path, codex_source = resolve_codex_cli_path()
                docker_path, docker_source = resolve_docker_cli_path()
        finally:
            for name, value in old_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.assertIsNone(codex_path)
        self.assertIsNone(docker_path)
        self.assertIn("unavailable", codex_source)
        self.assertIn("unavailable", docker_source)

    def test_env_paths_override_missing_path_lookup(self) -> None:
        old_env = {name: os.environ.get(name) for name in ("OMA7_CODEX_CLI_PATH", "CODEX_CLI_PATH", "OMA7_DOCKER_CLI_PATH", "DOCKER_CLI_PATH")}
        try:
            os.environ["OMA7_CODEX_CLI_PATH"] = r"C:\portable\codex.exe"
            os.environ["OMA7_DOCKER_CLI_PATH"] = r"C:\portable\docker.exe"
            probe = resolve_host_capability()
        finally:
            for name, value in old_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.assertEqual(probe.support, HostCapabilitySupport.SUPPORTED)
        self.assertEqual(probe.codex_cli_path, r"C:\portable\codex.exe")
        self.assertEqual(probe.docker_cli_path, r"C:\portable\docker.exe")

    def test_npm_install_location_is_detected_on_windows(self) -> None:
        old_env = {name: os.environ.get(name) for name in ("APPDATA", "LOCALAPPDATA", "OMA7_CODEX_CLI_PATH", "CODEX_CLI_PATH")}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                appdata = Path(tmp) / "App Data" / "Roaming"
                npm_dir = appdata / "npm"
                npm_dir.mkdir(parents=True)
                codex_cmd = npm_dir / "codex.cmd"
                codex_cmd.write_text("@echo off\r\n", encoding="utf-8")
                os.environ["APPDATA"] = str(appdata)
                os.environ.pop("LOCALAPPDATA", None)
                os.environ.pop("OMA7_CODEX_CLI_PATH", None)
                os.environ.pop("CODEX_CLI_PATH", None)
                probe = resolve_host_capability(explicit_docker_cli=r"C:\docker\docker.exe")
        finally:
            for name, value in old_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.assertEqual(probe.support, HostCapabilitySupport.SUPPORTED)
        self.assertEqual(probe.codex_cli_path, str(codex_cmd))
        self.assertEqual(probe.codex_source, f"installed:{codex_cmd}")
        self.assertEqual(probe.docker_cli_path, r"C:\docker\docker.exe")

    def test_windows_cmd_probe_wraps_script_path_with_spaces(self) -> None:
        with patch("oma7.host_portability.sys.platform", "win32"), patch(
            "oma7.host_portability.subprocess.run"
        ) as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "codex-cli 0.test"
            run.return_value.stderr = ""
            candidate = Path(r"C:\Users\Igor B\AppData\Roaming\npm\codex.cmd")
            self.assertTrue(_probe_candidate_executable(candidate))
        self.assertEqual(
            [part.lower() if index == 0 else part for index, part in enumerate(run.call_args[0][0])],
            [
                r"c:\windows\system32\cmd.exe",
                "/d",
                "/s",
                "/c",
                f'""{candidate}" --version"',
            ],
        )


if __name__ == "__main__":
    unittest.main()
