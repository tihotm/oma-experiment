from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .lifecycle import (
    AcceptanceDecision,
    AcceptanceOutcome,
    ControlledLifecycleObservation,
    GateStatus,
    LifecycleState,
    evaluate_acceptance,
)
from .models import ResultStatus, Evidence
from .preflight import DEFAULT_RUNTIME_PINS
from .release_candidate import build_first_real_mission_spec
from .scope import ScopeDecision, ScopeChange, ScopeMutationKind, ScopeObjectType, ScopeOperation, ScopePolicy, ProvenanceAnchorInputs, build_provenance_anchor


@dataclass(frozen=True)
class E1AcceptancePrecheckReport:
    workspace: str
    acceptance: AcceptanceDecision
    baseline_no_op_ready: bool
    paused_first_real_g0: bool
    next_open_front: str
    contract_ready: bool

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["acceptance"] = {
            "outcome": self.acceptance.outcome.value,
            "lifecycle_state": self.acceptance.lifecycle_state.value,
            "reason": self.acceptance.reason,
            "applicable_evidence": None
            if self.acceptance.applicable_evidence is None
            else asdict(self.acceptance.applicable_evidence),
        }
        return data


def _canonical_observation(workspace: Path) -> ControlledLifecycleObservation:
    spec = build_first_real_mission_spec(workspace, DEFAULT_RUNTIME_PINS)
    provenance_anchor = build_provenance_anchor(
        ProvenanceAnchorInputs(
            subject_identity=spec.subject_identity,
            execution_context_identity=spec.execution_context_identity,
            verification_context_identity=spec.verification_context_identity,
            scope_policy_identity=spec.scope_policy_identity,
            run_id=spec.mission_identity.identity(),
            verifier_id=spec.verification_context_identity.verifier_identity,
            cost_ledger_head=None,
            cost_ledger_event_count=None,
            scope_decision=ScopeDecision.ALLOW,
            scope_change_id="e1-baseline-change",
        )
    ).identity
    from .scope import evaluate_scope_change

    scope_evaluation = evaluate_scope_change(
        ScopeChange(
            operation=ScopeOperation.MODIFY,
            before_path="src/oma7/experimental_acceptance.py",
            after_path="src/oma7/experimental_acceptance.py",
            before_object_type=ScopeObjectType.FILE,
            after_object_type=ScopeObjectType.FILE,
            before_identity="before",
            after_identity="after",
            mutation_kind=ScopeMutationKind.PRIMARY,
            explicitly_allowed=True,
            change_id="e1-baseline-change",
        ),
        ScopePolicy(allowed_scope_path_policy=("src/**", "tests/**", "docs/**", "scripts/**")),
        subject_identity=spec.subject_identity,
        materialization_identity=spec.materialization_identity,
        authorized_primary_change_ids=("e1-baseline-change",),
    )
    return ControlledLifecycleObservation(
        executor_state=LifecycleState.QUIESCENT,
        lifecycle_state=LifecycleState.VERIFICATION_PENDING,
        verifier_result=ResultStatus.PASS,
        evidence=Evidence(
            subject_identity=spec.subject_identity,
            materialization_identity=spec.materialization_identity,
            execution_context_identity=spec.execution_context_identity,
            verification_context_identity=spec.verification_context_identity,
            scope_policy_identity=spec.scope_policy_identity,
            provenance_anchor_identity=provenance_anchor,
            result=ResultStatus.PASS,
            schema_version="oma7.evidence/v1",
            verifier_id=spec.verification_context_identity.verifier_identity,
            run_id=spec.mission_identity.identity(),
        ),
        subject_identity=spec.subject_identity,
        materialization_identity=spec.materialization_identity,
        execution_context_identity=spec.execution_context_identity,
        verification_context_identity=spec.verification_context_identity,
        scope_policy_identity=spec.scope_policy_identity,
        provenance_anchor_identity=provenance_anchor,
        scope_evaluation=scope_evaluation,
        quiescence_status=GateStatus.PASS_,
        freeze_status=GateStatus.PASS_,
        integrity_status=GateStatus.PASS_,
        no_op_precheck_status=GateStatus.PASS_,
        no_op_expected_unchanged=True,
        metadata={"mission_id": spec.mission_identity.identity()},
    )


def build_e1_acceptance_precheck_report(workspace: Path) -> E1AcceptancePrecheckReport:
    observation = _canonical_observation(workspace)
    acceptance = evaluate_acceptance(observation)
    paused_first_real_g0 = (workspace / "docs" / "agent" / "CURRENT-WORK.md").read_text(encoding="utf-8")
    return E1AcceptancePrecheckReport(
        workspace=str(workspace),
        acceptance=acceptance,
        baseline_no_op_ready=acceptance.outcome == AcceptanceOutcome.NO_OP,
        paused_first_real_g0="PAUSED / MUST RESUME" in paused_first_real_g0,
        next_open_front="E3 immutable submission + context evidence",
        contract_ready=acceptance.outcome in {AcceptanceOutcome.NO_OP, AcceptanceOutcome.EVAL_DONE},
    )
