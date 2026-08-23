from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path


class HostCapabilitySupport(str, Enum):
    SUPPORTED = "SUPPORTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class HostCapabilityProbe:
    codex_cli_path: str | None
    docker_cli_path: str | None
    codex_source: str
    docker_source: str
    support: HostCapabilitySupport
    blockers: tuple[str, ...] = ()


def _candidate_from_env(*names: str) -> tuple[str, str] | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value, f"env:{name}"
    return None


def _candidate_from_standard_locations(candidates: tuple[Path, ...]) -> tuple[str, str] | None:
    for candidate in candidates:
        if candidate.exists():
            return str(candidate), f"installed:{candidate}"
    return None


def resolve_codex_cli_path(explicit: str | None = None) -> tuple[str | None, str]:
    if explicit:
        return explicit, "explicit"
    env_candidate = _candidate_from_env("OMA7_CODEX_CLI_PATH", "CODEX_CLI_PATH")
    if env_candidate:
        return env_candidate
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        standard_candidate = _candidate_from_standard_locations(
            (
                Path(local_app_data) / "Programs" / "Codex" / "codex.exe",
                Path(local_app_data) / "Programs" / "OpenAI Codex" / "codex.exe",
            )
        )
        if standard_candidate:
            return standard_candidate
    return None, "codex executable unavailable"


def resolve_docker_cli_path(explicit: str | None = None) -> tuple[str | None, str]:
    if explicit:
        return explicit, "explicit"
    env_candidate = _candidate_from_env("OMA7_DOCKER_CLI_PATH", "DOCKER_CLI_PATH")
    if env_candidate:
        return env_candidate
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        standard_candidate = _candidate_from_standard_locations(
            (
                Path(local_app_data) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe",
                Path(local_app_data) / "Programs" / "Docker Desktop" / "resources" / "bin" / "docker.exe",
            )
        )
        if standard_candidate:
            return standard_candidate
    for candidate in (
        Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"),
        Path(r"C:\Program Files\Docker Desktop\resources\bin\docker.exe"),
    ):
        if candidate.exists():
            return str(candidate), f"installed:{candidate}"
    return None, "docker executable unavailable"


def resolve_host_capability(*, explicit_codex_cli: str | None = None, explicit_docker_cli: str | None = None) -> HostCapabilityProbe:
    codex_cli_path, codex_source = resolve_codex_cli_path(explicit_codex_cli)
    docker_cli_path, docker_source = resolve_docker_cli_path(explicit_docker_cli)
    blockers: list[str] = []
    if codex_cli_path is None:
        blockers.append(codex_source)
    if docker_cli_path is None:
        blockers.append(docker_source)
    support = HostCapabilitySupport.SUPPORTED if not blockers else HostCapabilitySupport.BLOCKED
    return HostCapabilityProbe(
        codex_cli_path=codex_cli_path,
        docker_cli_path=docker_cli_path,
        codex_source=codex_source,
        docker_source=docker_source,
        support=support,
        blockers=tuple(blockers),
    )

