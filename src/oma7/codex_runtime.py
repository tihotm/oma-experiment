from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

from .host_portability import resolve_codex_cli_path
from .windows_cmd import build_windows_cmd_invocation


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


@dataclass(frozen=True)
class CodexHostPreflightProbe:
    returncode: int
    stdout: str
    stderr: str
    facts: dict[str, str]
    command: tuple[str, ...]
    cwd: str | None
    code_home: str | None

    @property
    def cli_capability(self) -> CodexCliCapability | None:
        raw = self.facts.get("CODEX_CLI_CAPABILITY")
        if raw is None:
            return None
        try:
            return CodexCliCapability(raw)
        except ValueError:
            return None

    @property
    def auth_status(self) -> CodexAuthStatus | None:
        raw = self.facts.get("CODEX_AUTH_STATUS")
        if raw is None:
            return None
        mapping = {
            "AUTH_READY": CodexAuthStatus.READY,
            "AUTH_NOT_READY": CodexAuthStatus.NOT_READY,
            "NOT_PROBED": CodexAuthStatus.NOT_PROBED,
        }
        return mapping.get(raw)

    @property
    def auth_ready(self) -> bool:
        return self.facts.get("CODEX_AUTH_READY") == "True"


def build_codex_environment(
    *,
    code_home: str | None = None,
    environment: Mapping[str, str] | None = None,
    include_api_key: bool = False,
) -> dict[str, str]:
    env = dict(os.environ if environment is None else environment)
    if code_home:
        env["CODEX_HOME"] = code_home
        env.setdefault("OMA7_EPHEMERAL_CODEX_HOME", code_home)
    elif env.get("OMA7_EPHEMERAL_CODEX_HOME") and not env.get("CODEX_HOME"):
        env["CODEX_HOME"] = str(env["OMA7_EPHEMERAL_CODEX_HOME"])
    elif env.get("CODEX_HOME") and not env.get("OMA7_EPHEMERAL_CODEX_HOME"):
        env["OMA7_EPHEMERAL_CODEX_HOME"] = str(env["CODEX_HOME"])
    if not include_api_key:
        env.pop("CODEX_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
    return env


def _normalize_existing_directory(candidate: Path, *, cwd: str | None = None) -> Path | None:
    resolved = candidate.expanduser()
    if not resolved.is_absolute() and cwd:
        resolved = Path(cwd) / resolved
    try:
        resolved = resolved.resolve(strict=False)
    except OSError:
        pass
    try:
        if resolved.exists() and resolved.is_dir():
            return resolved
    except OSError:
        return None
    return None


def resolve_ephemeral_codex_home(
    *,
    environment: Mapping[str, str] | None = None,
    cwd: str | None = None,
) -> str | None:
    env = os.environ if environment is None else environment
    explicit_candidates: list[tuple[str, str]] = []

    for key in ("OMA7_EPHEMERAL_CODEX_HOME", "CODEX_HOME"):
        value = env.get(key)
        if value:
            explicit_candidates.append((key, value))

    if explicit_candidates:
        for _, candidate in explicit_candidates:
            resolved = _normalize_existing_directory(Path(candidate), cwd=cwd)
            if resolved is not None:
                return str(resolved)
        return None

    fallback_candidates: list[tuple[str, str]] = []

    for key in ("TEMP", "TMP"):
        value = env.get(key)
        if value:
            fallback_candidates.append((key, str(Path(value) / "oma7-ephemeral-codex-home")))

    userprofile = env.get("USERPROFILE")
    if userprofile:
        fallback_candidates.append(
            (
                "USERPROFILE",
                str(Path(userprofile) / "AppData" / "Local" / "Temp" / "oma7-ephemeral-codex-home"),
            )
        )

    fallback_candidates.append(("fallback", str(Path(tempfile.gettempdir()) / "oma7-ephemeral-codex-home")))

    seen: set[str] = set()
    for _, candidate in fallback_candidates:
        normalized = os.path.normcase(os.path.normpath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved = _normalize_existing_directory(Path(candidate), cwd=cwd)
        if resolved is not None:
            return str(resolved)
    return None


def codex_executable(explicit: str | None = None) -> str | None:
    resolved, _ = resolve_codex_cli_path(explicit)
    return resolved


def _auth_probe_debug_enabled() -> bool:
    return os.environ.get("OMA7_DEBUG_CODEX_AUTH_PROBE") == "1"


def _redacted_environment_snapshot(environment: Mapping[str, str]) -> dict[str, str | int]:
    snapshot: dict[str, str | int] = {}
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
        if key in environment:
            snapshot[key] = environment[key]
    snapshot["redacted_secret_key_count"] = sum(
        1
        for key in environment
        if key.upper().endswith(("_KEY", "_TOKEN", "_SECRET"))
        or "PASSWORD" in key.upper()
        or "CREDENTIAL" in key.upper()
        or "AUTH" in key.upper()
    )
    return snapshot


def _sanitize_probe_text(text: str, environment: Mapping[str, str]) -> str:
    sanitized = text
    for key, value in environment.items():
        if not value:
            continue
        if key.upper().endswith(("_KEY", "_TOKEN", "_SECRET")) or "PASSWORD" in key.upper() or "CREDENTIAL" in key.upper():
            sanitized = sanitized.replace(value, "<redacted>")
    sanitized = re.sub(r"(?i)(authorization|authentication|token|secret|password)\s*[:=]\s*[^\s]+", r"\1=<redacted>", sanitized)
    return sanitized[:5000]


def _parse_structured_output(output: str) -> dict[str, str]:
    stripped = output.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return {str(key): str(value) for key, value in parsed.items() if value is not None}
    facts: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        facts[key.strip()] = value.strip()
    return facts


def _emit_auth_probe_debug(payload: Mapping[str, object]) -> None:
    if _auth_probe_debug_enabled():
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)


def _build_command_line(codex: str, arguments: Sequence[str]) -> list[str]:
    command: list[str] = [codex, *arguments]
    if sys.platform == "win32" and Path(codex).suffix.lower() in {".cmd", ".bat"}:
        command = build_windows_cmd_invocation(codex, arguments)
    return command


def run_codex_command(
    codex: str,
    arguments: Sequence[str],
    *,
    code_home: str | None = None,
    environment: Mapping[str, str] | None = None,
    cwd: str | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    if code_home:
        try:
            Path(code_home).mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            return subprocess.CompletedProcess(
                [codex, *arguments],
                1,
                "",
                f"codex home inaccessible: {exc}",
            )
    env = build_codex_environment(code_home=code_home, environment=environment)
    command = _build_command_line(codex, arguments)
    try:
        run_kwargs = dict(
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=cwd,
        )
        result = subprocess.run(command, **run_kwargs)
    except PermissionError as exc:
        return subprocess.CompletedProcess(command, 1, "", f"codex command inaccessible: {exc}")
    return result


def run_host_codex_preflight_probe(
    *,
    preflight_script: str,
    code_home: str | None = None,
    environment: Mapping[str, str] | None = None,
    cwd: str | None = None,
    powershell: str | None = None,
) -> CodexHostPreflightProbe:
    env = build_codex_environment(code_home=code_home, environment=environment)
    command = [
        powershell or os.environ.get("OMA7_POWERSHELL") or os.environ.get("POWERSHELL") or "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        preflight_script,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, env=env, cwd=cwd)
    return CodexHostPreflightProbe(
        returncode=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
        facts=_parse_structured_output(result.stdout or ""),
        command=tuple(command),
        cwd=cwd,
        code_home=code_home,
    )


def codex_login_status(
    codex: str,
    *,
    code_home: str | None = None,
    environment: Mapping[str, str] | None = None,
    cwd: str | None = None,
) -> tuple[bool, str]:
    result = run_codex_command(codex, ["login", "status"], code_home=code_home, environment=environment, cwd=cwd)
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part).strip()
    return result.returncode == 0, output or "codex login status unavailable"


def probe_codex_runtime(
    *,
    explicit_codex: str | None = None,
    code_home: str | None = None,
    environment: Mapping[str, str] | None = None,
    cwd: str | None = None,
) -> CodexRuntimeStatus:
    executable = codex_executable(explicit_codex)
    if executable is None:
        return CodexRuntimeStatus(
            cli_capability=CodexCliCapability.CLI_ABSENT,
            auth_status=CodexAuthStatus.NOT_PROBED,
            reason="codex executable unavailable",
        )
    ready, output = codex_login_status(executable, code_home=code_home, environment=environment, cwd=cwd)
    return CodexRuntimeStatus(
        cli_capability=CodexCliCapability.CLI_AVAILABLE,
        auth_status=CodexAuthStatus.READY if ready else CodexAuthStatus.NOT_READY,
        executable=executable,
        login_status_output=output,
        reason=output,
    )
