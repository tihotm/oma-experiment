from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .accounting import load_accounting_ledger
from .evidence_ledger import load_evidence, load_post_execution_records
from .lifecycle import ResumeClassification, classify_resume_state, load_durable_run_record, load_published_evidence
from .control_plane import SupervisorState, load_control_record


class RecoveryDisposition(str, Enum):
    CONTINUE = "CONTINUE"
    RETRY = "RETRY"
    FINALIZE = "FINALIZE"
    BLOCK = "BLOCK"
    NO_OP = "NO_OP"


@dataclass(frozen=True)
class RecoverySnapshot:
    control_record_path: Path
    run_record_path: Path
    evidence_path: Path
    accounting_run_id: str
    post_execution_run_id: str
    run_identity: object


@dataclass(frozen=True)
class RecoveryDecision:
    disposition: RecoveryDisposition
    control_state: SupervisorState | None
    resume_state: ResumeClassification
    reason: str


def classify_recovery(
    *,
    control_record_path: str | Path,
    run_record_path: str | Path,
    evidence_path: str | Path,
    accounting_run_id: str,
    post_execution_run_id: str,
    expected_run_identity,
) -> RecoveryDecision:
    control = load_control_record(control_record_path)
    evidence = load_published_evidence(evidence_path)
    run_record = load_durable_run_record(run_record_path)
    accounting = load_accounting_ledger(accounting_run_id)
    post_execution = load_post_execution_records(post_execution_run_id)

    if control is None:
        return RecoveryDecision(RecoveryDisposition.BLOCK, None, ResumeClassification.INVALID, "control record missing or invalid")
    if accounting_run_id != post_execution_run_id:
        return RecoveryDecision(RecoveryDisposition.BLOCK, control.state, ResumeClassification.CONFLICT, "accounting/run mismatch")

    resume_state = classify_resume_state(run_record, evidence, expected_run_identity)
    if resume_state == ResumeClassification.CONFLICT:
        return RecoveryDecision(RecoveryDisposition.BLOCK, control.state, resume_state, "persisted run identity conflict")
    if resume_state == ResumeClassification.DONE and accounting.is_valid():
        return RecoveryDecision(RecoveryDisposition.NO_OP, control.state, resume_state, "already finalized")
    if control.state in {SupervisorState.PENDING, SupervisorState.RUNNING, SupervisorState.VERIFYING, SupervisorState.RETRYABLE_FAILURE}:
        if control.current_attempt_id is None and control.state != SupervisorState.PENDING:
            return RecoveryDecision(RecoveryDisposition.RETRY, control.state, resume_state, "missing current attempt after restart")
        if evidence is None and control.state == SupervisorState.VERIFYING:
            return RecoveryDecision(RecoveryDisposition.RETRY, control.state, resume_state, "verification evidence missing")
        if evidence is not None and len(post_execution) == 0:
            return RecoveryDecision(RecoveryDisposition.CONTINUE, control.state, resume_state, "post-execution chain not yet persisted")
        return RecoveryDecision(RecoveryDisposition.CONTINUE, control.state, resume_state, "recoverable control state")
    if control.state in {SupervisorState.ACCEPTED, SupervisorState.TERMINAL_FAILURE, SupervisorState.ESCALATION_REQUIRED}:
        return RecoveryDecision(RecoveryDisposition.NO_OP, control.state, resume_state, "terminal control state")
    return RecoveryDecision(RecoveryDisposition.BLOCK, control.state, resume_state, "unclassified recovery state")
