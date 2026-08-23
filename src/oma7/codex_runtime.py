from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
import subprocess
from pathlib import Path

from .host_portability import resolve_codex_cli_path


class CodexCliCapability(str, Enum):
    CLI_ABSENT = "CLI_ABSENT"
    CLI_AVAILABLE = "CLI_AVAILABLE"


class CodexAuthStatus(str, Enum):
    NOT_PROBED = "NOT_PROBED"
    NOT_READY = "NOT_READY"
    READY = "READY"


@dataclass(frozen=True)
class CodexRuntimeStatus:
    cli_capability: CodexCliCapability
    auth_status: CodexAuthStatus
    executable: str | None = None
    login_status_output: str | None = None
    reason: str | None = None

    @property
    def cli_available(self) -> bool:
        return self.cli_capability == CodexCliCapability.CLI_AVAILABLE

    @property
    def auth_ready(self) -> bool:
        return self.auth_status == CodexAuthStatus.READY


def codex_executable(explicit: str | None = None) -> str | None:
    resolved, _ = resolve_codex_cli_path(explicit)
    return resolved


def codex_login_status(codex: str, *, code_home: str | None = None) -> tuple[bool, str]:
    env = os.environ.copy()
    if code_home:
        env["CODEX_HOME"] = code_home
    result = subprocess.run(
        [codex, "login", "status"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part).strip()
    return result.returncode == 0, output or "codex login status unavailable"


def probe_codex_runtime(*, explicit_codex: str | None = None, code_home: str | None = None) -> CodexRuntimeStatus:
    executable = codex_executable(explicit_codex)
    if executable is None:
        return CodexRuntimeStatus(
            cli_capability=CodexCliCapability.CLI_ABSENT,
            auth_status=CodexAuthStatus.NOT_PROBED,
            reason="codex executable unavailable",
        )
    ready, output = codex_login_status(executable, code_home=code_home)
    return CodexRuntimeStatus(
        cli_capability=CodexCliCapability.CLI_AVAILABLE,
        auth_status=CodexAuthStatus.READY if ready else CodexAuthStatus.NOT_READY,
        executable=executable,
        login_status_output=output,
        reason=output,
    )
