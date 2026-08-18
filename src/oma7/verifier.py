from __future__ import annotations

from pathlib import Path

from .models import Evidence, EvidenceApplicability, ResultStatus


def verify_evidence(
    evidence: Evidence,
    subject_identity,
    materialization_identity,
    execution_context_identity,
    verification_context_identity,
    scope_policy_identity,
    provenance_anchor_identity,
    result: ResultStatus,
) -> EvidenceApplicability:
    if not evidence.is_valid_schema():
        return EvidenceApplicability(
            subject_identity=None,
            materialization_identity=None,
            execution_context_identity=None,
            verification_context_identity=None,
            scope_policy_identity=None,
            provenance_anchor_identity=None,
            result=ResultStatus.UNKNOWN,
        )
    return EvidenceApplicability(
        subject_identity=evidence.subject_identity
        if evidence.subject_identity == subject_identity
        else None,
        materialization_identity=evidence.materialization_identity
        if evidence.materialization_identity == materialization_identity
        else None,
        execution_context_identity=evidence.execution_context_identity
        if evidence.execution_context_identity == execution_context_identity
        else None,
        verification_context_identity=evidence.verification_context_identity
        if evidence.verification_context_identity == verification_context_identity
        else None,
        scope_policy_identity=evidence.scope_policy_identity
        if evidence.scope_policy_identity == scope_policy_identity
        else None,
        provenance_anchor_identity=evidence.provenance_anchor_identity
        if evidence.provenance_anchor_identity == provenance_anchor_identity
        else None,
        result=result,
    )


def verify_snapshot_is_copy(snapshot_dir: str | Path, original_dir: str | Path) -> bool:
    snap = Path(snapshot_dir).resolve()
    orig = Path(original_dir).resolve()
    return snap != orig and snap.exists() and orig.exists()
