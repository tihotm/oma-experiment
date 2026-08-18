from __future__ import annotations

from pathlib import Path

from .models import Evidence, EvidenceApplicability, ResultStatus


def verify_evidence(
    evidence: Evidence,
    subject_identity,
    verification_context_identity,
    result: ResultStatus,
) -> EvidenceApplicability:
    return EvidenceApplicability(
        same_subject_identity=evidence.subject_identity == subject_identity,
        same_verification_context_identity=(
            evidence.verification_context_identity == verification_context_identity
        ),
        result=result,
    )


def verify_snapshot_is_copy(snapshot_dir: str | Path, original_dir: str | Path) -> bool:
    snap = Path(snapshot_dir).resolve()
    orig = Path(original_dir).resolve()
    return snap != orig and snap.exists() and orig.exists()

