from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .control_plane import AttemptIdentity
from .accounting import (
    AccountingEventKind,
    append_cost_entry,
    cost_ledger_event_count,
    cost_ledger_head,
    human_intervention_summary,
)
from .evidence_ledger import append_evidence
from .lifecycle import ControlledLifecycleObservation, evidence_publication_payload, publish_atomic_evidence
from .models import (
    ExecutionContextIdentity,
    Evidence,
    MissionIdentity,
    QualificationState,
    ResultStatus,
)


POST_EXECUTION_SCHEMA = "oma7.post-execution/v1"


@dataclass(frozen=True)
class PersistedExecutionArtifacts:
    evidence: Evidence
    evidence_path: str
    accounting_head: str | None
    accounting_event_count: int | None
    post_execution_records: tuple[object, ...] = ()


def _canonical(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if is_dataclass(value):
        return {
            f.name: _canonical(getattr(value, f.name))
            for f in fields(value)
            if getattr(value, f.name) is not None
        }
    raise TypeError(f"Unsupported canonical value: {type(value)!r}")


def _digest_payload(payload: Any) -> str:
    raw = json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class G0Result:
    state: QualificationState
    reason: str
    result: ResultStatus


@dataclass(frozen=True)
class G0Record:
    schema_version: str
    mission_identity: MissionIdentity
    attempt_identity: AttemptIdentity
    execution_context_identity: ExecutionContextIdentity
    evidence: Evidence
    result: G0Result

    def identity(self) -> str:
        return _digest_payload(self)

    def is_real_execution(self) -> bool:
        return self.result.result == ResultStatus.PASS

    def is_eligible(self) -> bool:
        if self.schema_version != POST_EXECUTION_SCHEMA:
            return False
        if self.result.result != ResultStatus.PASS:
            return False
        if self.evidence.predicate.get("kind") != "real-execution":
            return False
        if self.evidence.result != ResultStatus.PASS:
            return False
        if self.evidence.subject_identity is None or self.evidence.materialization_identity is None:
            return False
        if self.evidence.execution_context_identity != self.execution_context_identity:
            return False
        if self.mission_identity.subject_identity != self.evidence.subject_identity:
            return False
        if self.mission_identity.materialization_identity != self.evidence.materialization_identity:
            return False
        if self.mission_identity.execution_context_identity != self.execution_context_identity:
            return False
        return True


@dataclass(frozen=True)
class A1Result:
    state: QualificationState
    reason: str


@dataclass(frozen=True)
class A1Record:
    schema_version: str
    g0_record: G0Record
    result: A1Result

    def identity(self) -> str:
        return _digest_payload(self)

    def is_eligible(self) -> bool:
        return self.schema_version == POST_EXECUTION_SCHEMA and self.g0_record.is_eligible() and self.result.state == QualificationState.QUALIFIED


@dataclass(frozen=True)
class QualifiedPairRecord:
    schema_version: str
    g0_record: G0Record
    a1_record: A1Record

    def identity(self) -> str:
        return _digest_payload(self)

    def is_eligible(self) -> bool:
        if self.schema_version != POST_EXECUTION_SCHEMA:
            return False
        if not self.g0_record.is_eligible() or not self.a1_record.is_eligible():
            return False
        if self.g0_record.mission_identity.identity() != self.a1_record.g0_record.mission_identity.identity():
            return False
        if self.g0_record.attempt_identity.identity() != self.a1_record.g0_record.attempt_identity.identity():
            return False
        if self.g0_record.execution_context_identity != self.a1_record.g0_record.execution_context_identity:
            return False
        return True


def evaluate_g0(
    *,
    mission_identity: MissionIdentity,
    attempt_identity: AttemptIdentity,
    execution_context_identity: ExecutionContextIdentity,
    evidence: Evidence,
) -> G0Result:
    if attempt_identity.run_id != evidence.run_id:
        return G0Result(state=QualificationState.EXECUTION_FAILED, reason="run mismatch", result=ResultStatus.FAIL)
    if evidence.predicate.get("kind") != "real-execution":
        return G0Result(state=QualificationState.EXECUTION_FAILED, reason="synthetic or fixture evidence", result=ResultStatus.FAIL)
    if evidence.result != ResultStatus.PASS:
        return G0Result(state=QualificationState.EXECUTION_FAILED, reason="evidence not PASS", result=evidence.result)
    if evidence.execution_context_identity != execution_context_identity:
        return G0Result(state=QualificationState.EXECUTION_FAILED, reason="execution context mismatch", result=ResultStatus.FAIL)
    if mission_identity.subject_identity != evidence.subject_identity:
        return G0Result(state=QualificationState.EXCLUDED_GOLD_ORACLE_MISMATCH, reason="subject mismatch", result=ResultStatus.FAIL)
    if mission_identity.materialization_identity != evidence.materialization_identity:
        return G0Result(state=QualificationState.EXCLUDED_GOLD_APPLY_FAILURE, reason="materialization mismatch", result=ResultStatus.FAIL)
    if mission_identity.execution_context_identity != execution_context_identity:
        return G0Result(state=QualificationState.EXECUTION_FAILED, reason="mission execution mismatch", result=ResultStatus.FAIL)
    return G0Result(state=QualificationState.QUALIFIED, reason="g0 eligible", result=ResultStatus.PASS)


def build_g0_record(
    *,
    mission_identity: MissionIdentity,
    attempt_identity: AttemptIdentity,
    execution_context_identity: ExecutionContextIdentity,
    evidence: Evidence,
) -> G0Record:
    result = evaluate_g0(
        mission_identity=mission_identity,
        attempt_identity=attempt_identity,
        execution_context_identity=execution_context_identity,
        evidence=evidence,
    )
    return G0Record(
        schema_version=POST_EXECUTION_SCHEMA,
        mission_identity=mission_identity,
        attempt_identity=attempt_identity,
        execution_context_identity=execution_context_identity,
        evidence=evidence,
        result=result,
    )


def build_a1_record(g0_record: G0Record) -> A1Record:
    result = A1Result(
        state=QualificationState.QUALIFIED if g0_record.is_eligible() else QualificationState.EXECUTION_FAILED,
        reason="a1 derived from g0" if g0_record.is_eligible() else "g0 not eligible",
    )
    return A1Record(schema_version=POST_EXECUTION_SCHEMA, g0_record=g0_record, result=result)


def build_qualified_pair_record(g0_record: G0Record, a1_record: A1Record) -> QualifiedPairRecord:
    return QualifiedPairRecord(schema_version=POST_EXECUTION_SCHEMA, g0_record=g0_record, a1_record=a1_record)


def provenance_chain_reconstructible(g0_record: G0Record, a1_record: A1Record, qualified_pair: QualifiedPairRecord) -> bool:
    return g0_record.is_eligible() and a1_record.is_eligible() and qualified_pair.is_eligible()


def persist_canonical_execution_artifacts(
    *,
    run_id: str,
    evidence: Evidence,
    base_dir: str | Path = "evidence",
    accounting_cost_units: int | None = None,
    accounting_reason: str = "execution",
    accounting_kind: AccountingEventKind = AccountingEventKind.EXECUTION,
) -> PersistedExecutionArtifacts:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)

    if evidence.run_id is not None and evidence.run_id != run_id:
        raise ValueError("evidence/run mismatch")

    evidence_path = base / f"{run_id}.json"
    if accounting_cost_units is not None:
        append_cost_entry(
            run_id,
            cost_units=accounting_cost_units,
            kind=accounting_kind,
            reason=accounting_reason,
            evidence_reference=str(evidence_path),
            base_dir=base,
        )

    accounting_head = cost_ledger_head(run_id, base)
    accounting_event_count = cost_ledger_event_count(run_id, base)
    evidence_summary = human_intervention_summary(run_id, base)
    normalized_evidence = replace(
        evidence,
        run_id=run_id,
        cost_ledger_head=accounting_head,
        cost_ledger_event_count=accounting_event_count,
        human_intervention_summary=evidence.human_intervention_summary if evidence.human_intervention_summary is not None else evidence_summary,
    )
    if evidence.cost_ledger_head is not None and evidence.cost_ledger_head != accounting_head:
        raise ValueError("evidence cost ledger head mismatch")
    if evidence.cost_ledger_event_count is not None and evidence.cost_ledger_event_count != accounting_event_count:
        raise ValueError("evidence cost ledger count mismatch")
    publish_atomic_evidence(evidence_path, evidence_publication_payload(normalized_evidence))
    append_evidence(run_id, normalized_evidence, base)
    return PersistedExecutionArtifacts(
        evidence=normalized_evidence,
        evidence_path=str(evidence_path),
        accounting_head=accounting_head,
        accounting_event_count=accounting_event_count,
    )
