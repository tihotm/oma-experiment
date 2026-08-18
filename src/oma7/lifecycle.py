from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
from typing import Any

from .models import (
    Evidence,
    EvidenceApplicability,
    ExecutionContextIdentity,
    MaterializationIdentity,
    ProvenanceAnchorIdentity,
    ResultStatus,
    ScopePolicyIdentity,
    SubjectIdentity,
    VerificationContextIdentity,
)


class LifecycleState(str, Enum):
    PREPARED = "PREPARED"
    RUNNING = "RUNNING"
    EXECUTOR_TERMINATED = "EXECUTOR_TERMINATED"
    QUIESCENCE_PENDING = "QUIESCENCE_PENDING"
    QUIESCENT = "QUIESCENT"
    FROZEN = "FROZEN"
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    VERIFIED_PASS = "VERIFIED_PASS"
    VERIFIED_FAIL = "VERIFIED_FAIL"
    EVIDENCE_PENDING = "EVIDENCE_PENDING"
    EVAL_DONE = "EVAL_DONE"
    RETRY_REQUIRED = "RETRY_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class AcceptanceOutcome(str, Enum):
    EVAL_DONE = "EVAL_DONE"
    NO_OP = "NO_OP"
    NOT_ACCEPTED = "NOT_ACCEPTED"


class GateStatus(str, Enum):
    PASS_ = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass(frozen=True)
class ControlledLifecycleObservation:
    executor_state: LifecycleState
    lifecycle_state: LifecycleState
    verifier_result: ResultStatus
    evidence: Evidence | None
    subject_identity: SubjectIdentity | None
    materialization_identity: MaterializationIdentity | None
    execution_context_identity: ExecutionContextIdentity | None
    verification_context_identity: VerificationContextIdentity | None
    scope_policy_identity: ScopePolicyIdentity | None
    provenance_anchor_identity: ProvenanceAnchorIdentity | None
    quiescence_status: GateStatus = GateStatus.NOT_IMPLEMENTED
    freeze_status: GateStatus = GateStatus.NOT_IMPLEMENTED
    integrity_status: GateStatus = GateStatus.NOT_IMPLEMENTED
    no_op_precheck_status: GateStatus = GateStatus.NOT_IMPLEMENTED
    no_op_expected_unchanged: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AcceptanceDecision:
    outcome: AcceptanceOutcome
    lifecycle_state: LifecycleState
    reason: str
    applicable_evidence: EvidenceApplicability | None = None


SUPPORTED_EVIDENCE_SCHEMA = "oma7.evidence/v1"


def _safe_gate(status: GateStatus) -> bool:
    return status == GateStatus.PASS_


def _is_supported_evidence(evidence: Evidence | None) -> bool:
    return evidence is not None and evidence.schema_version == SUPPORTED_EVIDENCE_SCHEMA


def evaluate_acceptance(
    observation: ControlledLifecycleObservation,
) -> AcceptanceDecision:
    if observation.executor_state == LifecycleState.RUNNING:
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NOT_ACCEPTED,
            lifecycle_state=observation.lifecycle_state,
            reason="executor running",
        )
    if observation.lifecycle_state in {
        LifecycleState.RETRY_REQUIRED,
        LifecycleState.REVIEW_REQUIRED,
        LifecycleState.BLOCKED,
        LifecycleState.VERIFIED_FAIL,
        LifecycleState.EXECUTION_FAILED,
    }:
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NOT_ACCEPTED,
            lifecycle_state=observation.lifecycle_state,
            reason=f"terminal or retry lifecycle: {observation.lifecycle_state.value}",
        )
    if not _safe_gate(observation.freeze_status) or not _safe_gate(observation.integrity_status):
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NOT_ACCEPTED,
            lifecycle_state=observation.lifecycle_state,
            reason="mandatory lifecycle gate not passed",
        )
    if observation.quiescence_status != GateStatus.PASS_:
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NOT_ACCEPTED,
            lifecycle_state=observation.lifecycle_state,
            reason="quiescence not confirmed",
        )
    if observation.verifier_result != ResultStatus.PASS:
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NOT_ACCEPTED,
            lifecycle_state=observation.lifecycle_state,
            reason="verifier did not pass",
        )
    if not _is_supported_evidence(observation.evidence):
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NOT_ACCEPTED,
            lifecycle_state=observation.lifecycle_state,
            reason="unsupported or missing evidence",
        )
    if any(
        value is None
        for value in (
            observation.subject_identity,
            observation.materialization_identity,
            observation.execution_context_identity,
            observation.verification_context_identity,
            observation.scope_policy_identity,
            observation.provenance_anchor_identity,
        )
    ):
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NOT_ACCEPTED,
            lifecycle_state=observation.lifecycle_state,
            reason="mandatory identity missing or unknown",
        )
    applicability = EvidenceApplicability(
        subject_identity=observation.evidence.subject_identity
        if observation.evidence.subject_identity == observation.subject_identity
        else None,
        materialization_identity=observation.evidence.materialization_identity
        if observation.evidence.materialization_identity == observation.materialization_identity
        else None,
        execution_context_identity=observation.evidence.execution_context_identity
        if observation.evidence.execution_context_identity == observation.execution_context_identity
        else None,
        verification_context_identity=observation.evidence.verification_context_identity
        if observation.evidence.verification_context_identity == observation.verification_context_identity
        else None,
        scope_policy_identity=observation.evidence.scope_policy_identity
        if observation.evidence.scope_policy_identity == observation.scope_policy_identity
        else None,
        provenance_anchor_identity=observation.evidence.provenance_anchor_identity
        if observation.evidence.provenance_anchor_identity == observation.provenance_anchor_identity
        else None,
        result=observation.evidence.result,
    )
    if not applicability.authorizes_acceptance:
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NOT_ACCEPTED,
            lifecycle_state=observation.lifecycle_state,
            reason="evidence not applicable",
            applicable_evidence=applicability,
        )
    if observation.no_op_precheck_status == GateStatus.PASS_:
        if observation.no_op_expected_unchanged is not True:
            return AcceptanceDecision(
                outcome=AcceptanceOutcome.NOT_ACCEPTED,
                lifecycle_state=LifecycleState.REVIEW_REQUIRED
                if observation.no_op_expected_unchanged is False
                else observation.lifecycle_state,
                reason="no-op path requires positive unchanged verification",
                applicable_evidence=applicability,
            )
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NO_OP,
            lifecycle_state=LifecycleState.EVAL_DONE,
            reason="legitimate no-op accepted",
            applicable_evidence=applicability,
        )
    return AcceptanceDecision(
        outcome=AcceptanceOutcome.EVAL_DONE,
        lifecycle_state=LifecycleState.EVAL_DONE,
        reason="applicable evidence accepted",
        applicable_evidence=applicability,
    )


def lifecycle_state_from_decision(decision: AcceptanceDecision) -> LifecycleState:
    return decision.lifecycle_state


def _deterministic_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class AtomicEvidencePublicationResult:
    published: bool
    path: Path
    directory_fsync_supported: bool
    conflict: bool = False


def publish_atomic_evidence(
    target_path: str | Path,
    payload: dict[str, Any],
) -> AtomicEvidencePublicationResult:
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _deterministic_json(payload)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            return AtomicEvidencePublicationResult(True, path, False)
        return AtomicEvidencePublicationResult(False, path, False, conflict=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(content)
        try:
            fh.flush()
        except Exception:
            pass
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    tmp.replace(path)
    directory_fsync_supported = False
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
            directory_fsync_supported = True
        finally:
            os.close(dir_fd)
    except OSError:
        directory_fsync_supported = False
    return AtomicEvidencePublicationResult(True, path, directory_fsync_supported)


def load_published_evidence(path: str | Path) -> dict[str, Any] | None:
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload
