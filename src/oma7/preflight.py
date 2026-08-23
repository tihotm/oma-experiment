from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from hashlib import sha256
import json
import re
import socket
import tempfile
from pathlib import Path
from typing import Any

from .models import ExecutionContextIdentity


DEFAULT_CODEX_IMAGE_REF = "sha256:1d20675dba6987fd196f57c8be142683e6610ed2d72428c50ff5dfe2b758b381"


class PreflightResult(str, Enum):
    PASS = "PASS"
    ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"


class ProductionPreflightResult(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RuntimePins:
    codex_sha256: str
    codex_version: str
    model: str
    reasoning_level: str
    harness_commit_or_digest: str
    harness_configuration_digest: str
    dataset_revision: str
    dependency_lock_digest: str
    container_image_digest: str
    toolchain_identity: str

    def _is_immutable_token(self, value: str) -> bool:
        if not value or value in {"latest", "main", "v1"}:
            return False
        if value.startswith("image:"):
            return False
        return bool(
            re.fullmatch(r"[0-9a-f]{64}", value)
            or re.fullmatch(r"[0-9a-f]{7,40}", value)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", value)
            or re.fullmatch(r"[^:]+@sha256:[0-9a-f]{64}", value)
        )

    def is_valid(self) -> bool:
        required = (
            self.codex_sha256,
            self.codex_version,
            self.model,
            self.reasoning_level,
            self.harness_commit_or_digest,
            self.harness_configuration_digest,
            self.dataset_revision,
            self.dependency_lock_digest,
            self.container_image_digest,
            self.toolchain_identity,
        )
        if not all(required):
            return False
        immutable_fields = {
            "codex_sha256",
            "harness_commit_or_digest",
            "harness_configuration_digest",
            "dataset_revision",
            "dependency_lock_digest",
            "container_image_digest",
            "toolchain_identity",
        }
        for name, value in (
            ("codex_sha256", self.codex_sha256),
            ("codex_version", self.codex_version),
            ("model", self.model),
            ("reasoning_level", self.reasoning_level),
            ("harness_commit_or_digest", self.harness_commit_or_digest),
            ("harness_configuration_digest", self.harness_configuration_digest),
            ("dataset_revision", self.dataset_revision),
            ("dependency_lock_digest", self.dependency_lock_digest),
            ("container_image_digest", self.container_image_digest),
            ("toolchain_identity", self.toolchain_identity),
        ):
            if name in immutable_fields and not self._is_immutable_token(value):
                return False
        return True


@dataclass(frozen=True)
class SandboxPreflightConfig:
    workspace: Path
    pins: RuntimePins
    approval_noninteractive: bool
    automatic_escalation_disabled: bool


@dataclass(frozen=True)
class ProductionPreflightConfig:
    workspace: Path
    pins: RuntimePins
    control_record: Any


@dataclass(frozen=True)
class SandboxPreflightResult:
    execution_context_id: str | None
    codex_version: str | None
    codex_sha256: str | None
    container_digest: str | None
    dataset_revision: str | None
    harness_identity: str | None
    workspace_write: bool
    outside_workspace_write_blocked: bool
    network_blocked: bool
    approval_noninteractive: bool
    automatic_escalation_disabled: bool
    pins_valid: bool
    result: PreflightResult
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ProductionExecutionPlan:
    result: ProductionPreflightResult
    execution_context_identity: ExecutionContextIdentity | None
    execution_context_id: str | None
    blocked_reasons: tuple[str, ...] = ()


def _canonicalize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [_canonicalize(item) for item in value]
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonicalize(value[key]) for key in sorted(value)}
    if is_dataclass(value):
        return {
            f.name: _canonicalize(getattr(value, f.name))
            for f in fields(value)
            if getattr(value, f.name) is not None
        }
    raise TypeError(f"Unsupported canonical value: {type(value)!r}")


def _digest_payload(payload: Any) -> str:
    raw = json.dumps(_canonicalize(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def execution_context_identity_from_pins(pins: RuntimePins) -> ExecutionContextIdentity:
    if not pins.is_valid():
        raise ValueError("runtime pins invalid")
    return ExecutionContextIdentity(
        environment_container_image_digest=pins.container_image_digest,
        codex_binary_digest=pins.codex_sha256,
        codex_version=pins.codex_version,
        model=pins.model,
        reasoning_level=pins.reasoning_level,
        harness_commit_or_digest=pins.harness_commit_or_digest,
        harness_configuration_digest=pins.harness_configuration_digest,
        dependency_lock_digest=pins.dependency_lock_digest,
        dataset_revision=pins.dataset_revision,
        toolchain_identity=pins.toolchain_identity,
    )


def execution_context_id_from_pins(pins: RuntimePins) -> str:
    return execution_context_identity_from_pins(pins).identity()


def _check_workspace_write(workspace: Path) -> bool:
    probe = workspace / ".oma7-preflight-write-probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _check_outside_workspace_write(workspace: Path) -> bool:
    candidates = [Path(tempfile.gettempdir()) / ".oma7-preflight-outside-probe"]
    try:
        parent_candidate = workspace.parent / ".oma7-preflight-outside-probe"
        if parent_candidate.resolve() != workspace.resolve():
            candidates.append(parent_candidate)
    except Exception:
        pass
    for outside in candidates:
        try:
            if outside.resolve().is_relative_to(workspace.resolve()):
                continue
        except Exception:
            pass
        try:
            outside.write_text("blocked?", encoding="utf-8")
            outside.unlink(missing_ok=True)
            return False
        except Exception:
            continue
    return True


def _check_traversal_write(workspace: Path) -> bool:
    probe = workspace / ".." / ".oma7-preflight-traversal-probe"
    try:
        probe.write_text("blocked?", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return False
    except Exception:
        return True


def _check_symlink_escape_write(workspace: Path) -> bool:
    try:
        target = Path(tempfile.gettempdir()) / ".oma7-preflight-symlink-target"
        link = workspace / ".oma7-preflight-symlink"
        target.write_text("ok", encoding="utf-8")
        try:
            if link.exists() or link.is_symlink():
                link.unlink(missing_ok=True)
            link.symlink_to(target)
        except Exception:
            return True
        try:
            escape = link / "escape.txt"
            escape.write_text("blocked?", encoding="utf-8")
            escape.unlink(missing_ok=True)
            return False
        except Exception:
            return True
        finally:
            link.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
    except Exception:
        return True


def _check_network_blocked() -> bool:
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=2):
            return False
    except Exception:
        return True


def run_sandbox_preflight(config: SandboxPreflightConfig) -> SandboxPreflightResult:
    failures: list[str] = []
    pins_valid = config.pins.is_valid()
    execution_context_id = execution_context_id_from_pins(config.pins) if pins_valid else None
    if not pins_valid:
        failures.append("pins invalid")
    workspace_write = _check_workspace_write(config.workspace)
    if not workspace_write:
        failures.append("workspace write failed")
    outside_blocked = _check_outside_workspace_write(config.workspace)
    if not outside_blocked:
        failures.append("outside-workspace write succeeded")
    traversal_blocked = _check_traversal_write(config.workspace)
    if not traversal_blocked:
        failures.append("traversal write succeeded")
    symlink_blocked = _check_symlink_escape_write(config.workspace)
    if not symlink_blocked:
        failures.append("symlink escape write succeeded")
    network_blocked = _check_network_blocked()
    if not network_blocked:
        failures.append("network access succeeded")
    if not config.approval_noninteractive:
        failures.append("approval interactive")
    if not config.automatic_escalation_disabled:
        failures.append("automatic escalation enabled")
    if not pins_valid:
        failures.append("missing or mutable runtime pins")
    result = PreflightResult.PASS if not failures else PreflightResult.ENVIRONMENT_BLOCKED
    return SandboxPreflightResult(
        execution_context_id=execution_context_id,
        codex_version=config.pins.codex_version,
        codex_sha256=config.pins.codex_sha256,
        container_digest=config.pins.container_image_digest,
        dataset_revision=config.pins.dataset_revision,
        harness_identity=f"{config.pins.harness_commit_or_digest}:{config.pins.harness_configuration_digest}",
        workspace_write=workspace_write,
        outside_workspace_write_blocked=outside_blocked,
        network_blocked=network_blocked,
        approval_noninteractive=config.approval_noninteractive,
        automatic_escalation_disabled=config.automatic_escalation_disabled,
        pins_valid=pins_valid,
        result=result,
        failure_reasons=tuple(failures),
    )


def make_dry_run_plan(config: ProductionPreflightConfig) -> ProductionExecutionPlan:
    from .control_plane import preflight_ready

    if not preflight_ready(config.control_record):
        return ProductionExecutionPlan(
            result=ProductionPreflightResult.BLOCKED,
            execution_context_identity=None,
            execution_context_id=None,
            blocked_reasons=("control record not ready",),
        )
    if config.control_record.mission_identity is None or config.control_record.execution_context_identity is None:
        return ProductionExecutionPlan(
            result=ProductionPreflightResult.BLOCKED,
            execution_context_identity=None,
            execution_context_id=None,
            blocked_reasons=("missing mission or execution identity",),
        )
    try:
        expected_execution = execution_context_identity_from_pins(config.pins)
    except ValueError:
        return ProductionExecutionPlan(
            result=ProductionPreflightResult.BLOCKED,
            execution_context_identity=config.control_record.execution_context_identity,
            execution_context_id=None,
            blocked_reasons=("invalid runtime pins",),
        )
    if expected_execution != config.control_record.execution_context_identity:
        return ProductionExecutionPlan(
            result=ProductionPreflightResult.BLOCKED,
            execution_context_identity=config.control_record.execution_context_identity,
            execution_context_id=None,
            blocked_reasons=("execution context mismatch",),
        )
    return ProductionExecutionPlan(
        result=ProductionPreflightResult.READY,
        execution_context_identity=config.control_record.execution_context_identity,
        execution_context_id=config.control_record.execution_context_identity.identity(),
    )


def run_production_preflight(config: ProductionPreflightConfig) -> ProductionPreflightResult:
    from .control_plane import preflight_ready

    if not preflight_ready(config.control_record):
        return ProductionPreflightResult.BLOCKED
    if config.control_record.mission_identity is None or config.control_record.execution_context_identity is None:
        return ProductionPreflightResult.BLOCKED
    try:
        expected_execution = execution_context_identity_from_pins(config.pins)
    except ValueError:
        return ProductionPreflightResult.BLOCKED
    if config.control_record.execution_context_identity != expected_execution:
        return ProductionPreflightResult.BLOCKED
    return ProductionPreflightResult.READY
