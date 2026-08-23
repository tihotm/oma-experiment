from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
from typing import Iterable

from .models import (
    ExecutionContextIdentity,
    MaterializationIdentity,
    ProvenanceAnchorIdentity,
    ScopePolicyIdentity,
    SubjectIdentity,
    VerificationContextIdentity,
)


class ScopeDecision(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class ScopeMutationKind(str, Enum):
    PRIMARY = "PRIMARY"
    GENERATED = "GENERATED"
    SECONDARY = "SECONDARY"


class ScopeOperation(str, Enum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    RENAME = "RENAME"
    REPLACE = "REPLACE"
    SYMLINK_CREATE = "SYMLINK_CREATE"
    SYMLINK_RETARGET = "SYMLINK_RETARGET"
    HARDLINK = "HARDLINK"
    MODE_CHANGE = "MODE_CHANGE"
    OBJECT_TYPE_CHANGE = "OBJECT_TYPE_CHANGE"


class ScopeObjectType(str, Enum):
    FILE = "FILE"
    DIRECTORY = "DIRECTORY"
    SYMLINK = "SYMLINK"
    HARDLINK = "HARDLINK"
    OTHER = "OTHER"


@dataclass(frozen=True)
class ScopePolicy:
    allowed_scope_path_policy: tuple[str, ...]
    high_risk_transitions_blocked: bool = True


@dataclass(frozen=True)
class ScopeChange:
    operation: ScopeOperation
    after_path: str
    before_path: str | None = None
    before_object_type: ScopeObjectType | None = None
    after_object_type: ScopeObjectType | None = None
    before_identity: str | None = None
    after_identity: str | None = None
    mutation_kind: ScopeMutationKind = ScopeMutationKind.PRIMARY
    parent_change_id: str | None = None
    explicitly_allowed: bool = False
    change_id: str | None = None


@dataclass(frozen=True)
class ScopeEvaluation:
    decision: ScopeDecision
    reason: str
    change: ScopeChange
    subject_identity: SubjectIdentity | None
    materialization_identity: MaterializationIdentity | None
    canonical_before_path: str | None
    canonical_after_path: str | None

    def is_valid_for(
        self,
        subject_identity: SubjectIdentity | None,
        materialization_identity: MaterializationIdentity | None,
    ) -> bool:
        return (
            self.subject_identity is not None
            and self.materialization_identity is not None
            and self.subject_identity == subject_identity
            and self.materialization_identity == materialization_identity
        )


@dataclass(frozen=True)
class ProvenanceAnchorInputs:
    subject_identity: SubjectIdentity
    execution_context_identity: ExecutionContextIdentity
    verification_context_identity: VerificationContextIdentity
    scope_policy_identity: ScopePolicyIdentity
    run_id: str | None = None
    verifier_id: str | None = None
    cost_ledger_head: str | None = None
    cost_ledger_event_count: int | None = None
    scope_decision: ScopeDecision | None = None
    scope_change_id: str | None = None
    namespace: str = "oma7:provenance-anchor:v1"


@dataclass(frozen=True)
class ProvenanceAnchor:
    identity: ProvenanceAnchorIdentity
    inputs: ProvenanceAnchorInputs


def _canonicalize(value):
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
    if hasattr(value, "__dataclass_fields__"):
        return {
            field_name: _canonicalize(getattr(value, field_name))
            for field_name in sorted(value.__dataclass_fields__)
            if getattr(value, field_name) is not None
        }
    raise TypeError(f"Unsupported canonical value: {type(value)!r}")


def _digest(payload) -> str:
    raw = json.dumps(_canonicalize(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def build_provenance_anchor(inputs: ProvenanceAnchorInputs) -> ProvenanceAnchor:
    if not all(
        (
            inputs.subject_identity,
            inputs.execution_context_identity,
            inputs.verification_context_identity,
            inputs.scope_policy_identity,
        )
    ):
        raise ValueError("missing required provenance inputs")
    anchor_payload = {
        "namespace": inputs.namespace,
        "subject_identity": inputs.subject_identity,
        "execution_context_identity": inputs.execution_context_identity,
        "verification_context_identity": inputs.verification_context_identity,
        "scope_policy_identity": inputs.scope_policy_identity,
        "run_id": inputs.run_id,
        "verifier_id": inputs.verifier_id,
        "cost_ledger_head": inputs.cost_ledger_head,
        "cost_ledger_event_count": inputs.cost_ledger_event_count,
        "scope_decision": inputs.scope_decision,
        "scope_change_id": inputs.scope_change_id,
    }
    identity = ProvenanceAnchorIdentity(
        anchor_type=inputs.namespace,
        immutable_anchor_identifier_digest=_digest(anchor_payload),
        provenance_root=inputs.run_id or inputs.subject_identity.identity(),
        event_count=inputs.cost_ledger_event_count,
        schema_information="oma7.provenance-anchor/v1",
    )
    return ProvenanceAnchor(identity=identity, inputs=inputs)


def canonicalize_scope_path(path: str | None) -> str | None:
    if path is None:
        return None
    raw = str(path).replace("\\", "/").strip()
    if not raw:
        return None
    candidate = PurePosixPath(raw)
    if candidate.is_absolute():
        return None
    parts: list[str] = []
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        if ":" in part:
            return None
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def _matches_allowed_path(path: str, allowed_patterns: Iterable[str]) -> bool:
    return any(fnmatchcase(path, pattern.replace("\\", "/")) for pattern in allowed_patterns)


def _is_high_risk_transition(change: ScopeChange) -> bool:
    if change.operation in {
        ScopeOperation.SYMLINK_CREATE,
        ScopeOperation.SYMLINK_RETARGET,
        ScopeOperation.HARDLINK,
        ScopeOperation.OBJECT_TYPE_CHANGE,
    }:
        return True
    if change.operation == ScopeOperation.REPLACE and (
        change.before_object_type in {ScopeObjectType.SYMLINK, ScopeObjectType.HARDLINK}
        or change.after_object_type in {ScopeObjectType.SYMLINK, ScopeObjectType.HARDLINK}
    ):
        return True
    if change.after_object_type == ScopeObjectType.SYMLINK:
        return True
    return False


def evaluate_scope_change(
    change: ScopeChange,
    policy: ScopePolicy,
    *,
    subject_identity: SubjectIdentity | None = None,
    materialization_identity: MaterializationIdentity | None = None,
    authorized_primary_change_ids: Iterable[str] = (),
) -> ScopeEvaluation:
    canonical_before = canonicalize_scope_path(change.before_path)
    canonical_after = canonicalize_scope_path(change.after_path)
    if canonical_after is None:
        return ScopeEvaluation(
            decision=ScopeDecision.BLOCK,
            reason="unresolved canonical path",
            change=change,
            subject_identity=subject_identity,
            materialization_identity=materialization_identity,
            canonical_before_path=canonical_before,
            canonical_after_path=canonical_after,
        )

    if change.mutation_kind in {ScopeMutationKind.GENERATED, ScopeMutationKind.SECONDARY}:
        parent_is_authorized = change.parent_change_id is not None and change.parent_change_id in set(
            authorized_primary_change_ids
        )
        if not (change.explicitly_allowed or parent_is_authorized):
            return ScopeEvaluation(
                decision=ScopeDecision.BLOCK,
                reason="unbound generated or secondary mutation",
                change=change,
                subject_identity=subject_identity,
                materialization_identity=materialization_identity,
                canonical_before_path=canonical_before,
                canonical_after_path=canonical_after,
            )

    if change.operation in {ScopeOperation.RENAME, ScopeOperation.REPLACE} and canonical_before is None:
        return ScopeEvaluation(
            decision=ScopeDecision.REVIEW,
            reason="rename or replace requires resolvable before path",
            change=change,
            subject_identity=subject_identity,
            materialization_identity=materialization_identity,
            canonical_before_path=canonical_before,
            canonical_after_path=canonical_after,
        )

    if change.operation in {
        ScopeOperation.SYMLINK_CREATE,
        ScopeOperation.SYMLINK_RETARGET,
        ScopeOperation.HARDLINK,
        ScopeOperation.OBJECT_TYPE_CHANGE,
    }:
        return ScopeEvaluation(
            decision=ScopeDecision.BLOCK,
            reason=f"high-risk transition: {change.operation.value.lower()}",
            change=change,
            subject_identity=subject_identity,
            materialization_identity=materialization_identity,
            canonical_before_path=canonical_before,
            canonical_after_path=canonical_after,
        )

    if canonical_before is not None and canonical_before != canonical_after:
        before_allowed = _matches_allowed_path(canonical_before, policy.allowed_scope_path_policy)
        after_allowed = _matches_allowed_path(canonical_after, policy.allowed_scope_path_policy)
        if change.operation == ScopeOperation.RENAME:
            if before_allowed and not after_allowed:
                return ScopeEvaluation(
                    decision=ScopeDecision.BLOCK,
                    reason="rename from allowed to forbidden path",
                    change=change,
                    subject_identity=subject_identity,
                    materialization_identity=materialization_identity,
                    canonical_before_path=canonical_before,
                    canonical_after_path=canonical_after,
                )
            if not before_allowed and after_allowed:
                return ScopeEvaluation(
                    decision=ScopeDecision.REVIEW,
                    reason="rename from forbidden to allowed path",
                    change=change,
                    subject_identity=subject_identity,
                    materialization_identity=materialization_identity,
                    canonical_before_path=canonical_before,
                    canonical_after_path=canonical_after,
                )

    if _is_high_risk_transition(change) and policy.high_risk_transitions_blocked:
        return ScopeEvaluation(
            decision=ScopeDecision.BLOCK,
            reason="high-risk transition blocked by policy",
            change=change,
            subject_identity=subject_identity,
            materialization_identity=materialization_identity,
            canonical_before_path=canonical_before,
            canonical_after_path=canonical_after,
        )

    if not _matches_allowed_path(canonical_after, policy.allowed_scope_path_policy):
        return ScopeEvaluation(
            decision=ScopeDecision.BLOCK,
            reason="path not authorized by scope policy",
            change=change,
            subject_identity=subject_identity,
            materialization_identity=materialization_identity,
            canonical_before_path=canonical_before,
            canonical_after_path=canonical_after,
        )

    if change.operation == ScopeOperation.MODE_CHANGE:
        return ScopeEvaluation(
            decision=ScopeDecision.ALLOW,
            reason="authorized mode change",
            change=change,
            subject_identity=subject_identity,
            materialization_identity=materialization_identity,
            canonical_before_path=canonical_before,
            canonical_after_path=canonical_after,
        )

    if change.mutation_kind is not ScopeMutationKind.PRIMARY and not change.explicitly_allowed:
        if change.parent_change_id is not None and change.parent_change_id in set(authorized_primary_change_ids):
            return ScopeEvaluation(
                decision=ScopeDecision.ALLOW,
                reason="generated or secondary mutation causally bound to authorized primary change",
                change=change,
                subject_identity=subject_identity,
                materialization_identity=materialization_identity,
                canonical_before_path=canonical_before,
                canonical_after_path=canonical_after,
            )
        return ScopeEvaluation(
            decision=ScopeDecision.REVIEW,
            reason="generated or secondary mutation requires explicit causal authorization",
            change=change,
            subject_identity=subject_identity,
            materialization_identity=materialization_identity,
            canonical_before_path=canonical_before,
            canonical_after_path=canonical_after,
        )

    return ScopeEvaluation(
        decision=ScopeDecision.ALLOW,
        reason="scope change authorized",
        change=change,
        subject_identity=subject_identity,
        materialization_identity=materialization_identity,
        canonical_before_path=canonical_before,
        canonical_after_path=canonical_after,
    )
