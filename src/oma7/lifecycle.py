from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from hashlib import sha256
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
from .scope import ScopeDecision, ScopeEvaluation


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
    scope_evaluation: ScopeEvaluation | None = None
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
    if observation.scope_evaluation is None:
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NOT_ACCEPTED,
            lifecycle_state=observation.lifecycle_state,
            reason="scope evaluation missing",
        )
    if not observation.scope_evaluation.is_valid_for(
        observation.subject_identity,
        observation.materialization_identity,
    ):
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NOT_ACCEPTED,
            lifecycle_state=observation.lifecycle_state,
            reason="scope evidence stale or invalid",
        )
    if observation.scope_evaluation.decision != ScopeDecision.ALLOW:
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.NOT_ACCEPTED,
            lifecycle_state=LifecycleState.REVIEW_REQUIRED
            if observation.scope_evaluation.decision == ScopeDecision.REVIEW
            else observation.lifecycle_state,
            reason=f"scope decision {observation.scope_evaluation.decision.value.lower()}",
            applicable_evidence=None,
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


def _deterministic_json(data: dict[str, Any], *, omit_none: bool = False) -> str:
    def _normalize(value: Any, omit_none: bool = False) -> Any:
        if value is None:
            return None
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, tuple):
            return [_normalize(item, omit_none=omit_none) for item in value]
        if isinstance(value, list):
            return [_normalize(item, omit_none=omit_none) for item in value]
        if isinstance(value, dict):
            result = {}
            for key in sorted(value):
                item = value[key]
                if omit_none and item is None:
                    continue
                result[str(key)] = _normalize(item, omit_none=omit_none)
            return result
        if is_dataclass(value):
            result = {}
            for f in fields(value):
                field_value = getattr(value, f.name)
                if omit_none and field_value is None:
                    continue
                result[f.name] = _normalize(field_value, omit_none=omit_none)
            return result
        raise TypeError(f"Unsupported canonical value: {type(value)!r}")

    return json.dumps(_normalize(data, omit_none=omit_none), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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


@dataclass(frozen=True)
class RunIdentity:
    instance_id: str
    phase: str
    replicate: str
    subject_identity: SubjectIdentity
    materialization_identity: MaterializationIdentity
    execution_context_identity: ExecutionContextIdentity
    verification_context_identity: VerificationContextIdentity
    scope_policy_identity: ScopePolicyIdentity
    provenance_anchor_identity: ProvenanceAnchorIdentity

    def identity(self) -> str:
        payload = {
            "execution_context_identity": self.execution_context_identity,
            "instance_id": self.instance_id,
            "materialization_identity": self.materialization_identity,
            "phase": self.phase,
            "provenance_anchor_identity": self.provenance_anchor_identity,
            "replicate": self.replicate,
            "scope_policy_identity": self.scope_policy_identity,
            "subject_identity": self.subject_identity,
            "verification_context_identity": self.verification_context_identity,
        }
        return sha256(_deterministic_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DurableRunRecord:
    schema_version: str
    run_identity: RunIdentity
    lifecycle_state: LifecycleState
    evidence_reference: str | None
    evidence_identity: str | None
    durability: dict[str, bool]

    def identity(self) -> str:
        payload = {
            "durability": self.durability,
            "evidence_identity": self.evidence_identity,
            "evidence_reference": self.evidence_reference,
            "lifecycle_state": self.lifecycle_state,
            "run_identity": self.run_identity.identity(),
            "schema_version": self.schema_version,
        }
        return sha256(_deterministic_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DurableWriteResult:
    path: Path
    file_fsync_performed: bool
    directory_fsync_performed: bool
    atomic_replace_used: bool


SUPPORTED_RUN_RECORD_SCHEMA = "oma7.run-record/v1"


class ResumeClassification(str, Enum):
    INVALID = "INVALID"
    RESUMABLE_FINALIZATION = "RESUMABLE_FINALIZATION"
    DONE = "DONE"
    CONFLICT = "CONFLICT"


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _evidence_payload_from_observation(observation: ControlledLifecycleObservation) -> dict[str, Any]:
    evidence = observation.evidence
    if evidence is None:
        return {}
    return {
        "schema_version": evidence.schema_version,
        "subject_identity": evidence.subject_identity,
        "materialization_identity": evidence.materialization_identity,
        "execution_context_identity": evidence.execution_context_identity,
        "verification_context_identity": evidence.verification_context_identity,
        "scope_policy_identity": evidence.scope_policy_identity,
        "provenance_anchor_identity": evidence.provenance_anchor_identity,
        "result": evidence.result.value,
        "verifier_id": evidence.verifier_id,
        "run_id": evidence.run_id,
        "cost_ledger_head": evidence.cost_ledger_head,
        "cost_ledger_event_count": evidence.cost_ledger_event_count,
        "human_intervention_summary": evidence.human_intervention_summary,
        "predicate": evidence.predicate,
    }


def evidence_publication_payload(evidence: Evidence) -> dict[str, Any]:
    payload = {
        "schema_version": evidence.schema_version,
        "subject_identity": evidence.subject_identity,
        "materialization_identity": evidence.materialization_identity,
        "execution_context_identity": evidence.execution_context_identity,
        "verification_context_identity": evidence.verification_context_identity,
        "scope_policy_identity": evidence.scope_policy_identity,
        "provenance_anchor_identity": evidence.provenance_anchor_identity,
        "result": evidence.result,
        "verifier_id": evidence.verifier_id,
        "run_id": evidence.run_id,
        "cost_ledger_head": evidence.cost_ledger_head,
        "cost_ledger_event_count": evidence.cost_ledger_event_count,
        "human_intervention_summary": evidence.human_intervention_summary,
        "predicate": evidence.predicate,
    }
    canonical = json.loads(_deterministic_json(payload, omit_none=True))
    return canonical


def _run_identity_payload(run_identity: RunIdentity) -> dict[str, Any]:
    payload = {
        "instance_id": run_identity.instance_id,
        "phase": run_identity.phase,
        "replicate": run_identity.replicate,
        "subject_identity": run_identity.subject_identity,
        "materialization_identity": run_identity.materialization_identity,
        "execution_context_identity": run_identity.execution_context_identity,
        "verification_context_identity": run_identity.verification_context_identity,
        "scope_policy_identity": run_identity.scope_policy_identity,
        "provenance_anchor_identity": run_identity.provenance_anchor_identity,
    }
    return json.loads(_deterministic_json(payload))


def _evidence_identity_from_payload(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    if payload.get("schema_version") != SUPPORTED_EVIDENCE_SCHEMA:
        return None
    try:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return None
    return sha256(raw.encode("utf-8")).hexdigest()


def write_durable_run_record(path: str | Path, record: DurableRunRecord) -> DurableWriteResult:
    payload = {
        "schema_version": record.schema_version,
        "run_identity": _run_identity_payload(record.run_identity),
        "lifecycle_state": record.lifecycle_state.value,
        "evidence_reference": record.evidence_reference,
        "evidence_identity": record.evidence_identity,
        "durability": record.durability,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    content = _deterministic_json(payload)
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    tmp.replace(target)
    file_fsync_performed = True
    directory_fsync_performed = False
    try:
        dir_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        directory_fsync_performed = True
    except OSError:
        directory_fsync_performed = False
    return DurableWriteResult(
        path=target,
        file_fsync_performed=file_fsync_performed,
        directory_fsync_performed=directory_fsync_performed,
        atomic_replace_used=True,
    )


def load_durable_run_record(path: str | Path) -> dict[str, Any] | None:
    payload = _safe_load_json(Path(path))
    if payload is None:
        return None
    if payload.get("schema_version") != SUPPORTED_RUN_RECORD_SCHEMA:
        return None
    return payload


def classify_resume_state(
    run_record: dict[str, Any] | None,
    evidence_payload: dict[str, Any] | None,
    expected_run_identity: RunIdentity,
) -> ResumeClassification:
    if run_record is None:
        return (
            ResumeClassification.RESUMABLE_FINALIZATION
            if _evidence_identity_from_payload(evidence_payload) is not None
            else ResumeClassification.INVALID
        )
    if run_record.get("schema_version") != SUPPORTED_RUN_RECORD_SCHEMA:
        return ResumeClassification.INVALID
    if run_record.get("run_identity") != _run_identity_payload(expected_run_identity):
        return ResumeClassification.CONFLICT
    if run_record.get("lifecycle_state") == LifecycleState.EVAL_DONE.value:
        if evidence_payload is None:
            return ResumeClassification.INVALID
        if run_record.get("evidence_identity") != _evidence_identity_from_payload(evidence_payload):
            return ResumeClassification.INVALID
        return ResumeClassification.DONE
    if evidence_payload is None:
        return ResumeClassification.RESUMABLE_FINALIZATION
    return ResumeClassification.RESUMABLE_FINALIZATION


def finalize_durable_done(
    run_record_path: str | Path,
    evidence_path: str | Path,
    expected_run_identity: RunIdentity,
    observation: ControlledLifecycleObservation,
) -> ResumeClassification:
    run_record = load_durable_run_record(run_record_path)
    evidence_payload = load_published_evidence(evidence_path)
    classification = classify_resume_state(run_record, evidence_payload, expected_run_identity)
    if classification not in {ResumeClassification.RESUMABLE_FINALIZATION, ResumeClassification.DONE}:
        return classification
    decision = evaluate_acceptance(observation)
    if decision.outcome not in {AcceptanceOutcome.EVAL_DONE, AcceptanceOutcome.NO_OP}:
        return ResumeClassification.INVALID
    if evidence_payload is None or observation.evidence is None:
        return ResumeClassification.INVALID
    if _evidence_identity_from_payload(evidence_payload) != observation.evidence.identity():
        return ResumeClassification.CONFLICT
    write_durable_run_record(
        run_record_path,
        DurableRunRecord(
            schema_version=SUPPORTED_RUN_RECORD_SCHEMA,
            run_identity=expected_run_identity,
            lifecycle_state=decision.lifecycle_state,
            evidence_reference=str(Path(evidence_path)),
            evidence_identity=observation.evidence.identity(),
            durability={
                "file_fsync_performed": True,
                "directory_fsync_performed": False,
                "atomic_replace_used": True,
            },
        ),
    )
    return ResumeClassification.DONE
