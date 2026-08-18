from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
import hashlib
import json
from typing import Any


SCHEMA_VERSION_SUPPORTED = "oma7.evidence/v1"


class ResultStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIP = "SKIP"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"


class QualificationState(str, Enum):
    QUALIFIED = "QUALIFIED"
    EXCLUDED_BASELINE_ORACLE_MISMATCH = "EXCLUDED_BASELINE_ORACLE_MISMATCH"
    EXCLUDED_GOLD_APPLY_FAILURE = "EXCLUDED_GOLD_APPLY_FAILURE"
    EXCLUDED_GOLD_ORACLE_MISMATCH = "EXCLUDED_GOLD_ORACLE_MISMATCH"
    EXCLUDED_GOLD_REGRESSION = "EXCLUDED_GOLD_REGRESSION"
    ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
    NONDETERMINISTIC_BASELINE = "NONDETERMINISTIC_BASELINE"
    NONDETERMINISTIC_GOLD = "NONDETERMINISTIC_GOLD"
    EXECUTION_FAILED = "EXECUTION_FAILED"


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
    raw = json.dumps(
        _canonicalize(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SubjectIdentity:
    git_tree: str
    git_commit: str | None = None
    path: str = "."
    schema_version: str = "oma7.subject/v1"

    def is_valid(self) -> bool:
        return bool(self.git_tree)

    def identity(self) -> str:
        if not self.is_valid():
            raise ValueError("subject identity requires git_tree")
        return _digest_payload(self)


@dataclass(frozen=True)
class MaterializationIdentity:
    subject_identity: SubjectIdentity
    canonical_root_descriptor: str
    symlink_topology: tuple[tuple[str, str], ...] = ()
    hardlink_topology: tuple[tuple[str, str], ...] = ()
    worktree_reference_identity: str | None = None
    mounted_reference_artifact_identities: tuple[str, ...] = ()
    cache_manifest_digest: str | None = None
    schema_version: str = "oma7.materialization/v1"

    def is_valid(self) -> bool:
        return bool(self.subject_identity and self.canonical_root_descriptor)

    def identity(self) -> str:
        if not self.is_valid():
            raise ValueError("materialization identity requires subject and root descriptor")
        return _digest_payload(self)


@dataclass(frozen=True)
class ExecutionContextIdentity:
    environment_container_image_digest: str
    codex_binary_digest: str
    codex_version: str
    model: str
    reasoning_level: str
    harness_commit_or_digest: str
    harness_configuration_digest: str
    dependency_lock_digest: str
    dataset_revision: str
    toolchain_identity: str
    schema_version: str = "oma7.execution-context/v1"

    def missing_required(self) -> list[str]:
        missing = []
        for item in (
            "environment_container_image_digest",
            "codex_binary_digest",
            "codex_version",
            "model",
            "reasoning_level",
            "harness_commit_or_digest",
            "harness_configuration_digest",
            "dependency_lock_digest",
            "dataset_revision",
            "toolchain_identity",
        ):
            if not getattr(self, item):
                missing.append(item)
        return missing

    def is_valid(self) -> bool:
        return not self.missing_required()

    def identity(self) -> str:
        missing = self.missing_required()
        if missing:
            raise ValueError(f"execution context missing required fields: {missing}")
        return _digest_payload(self)


@dataclass(frozen=True)
class VerificationContextIdentity:
    dataset_revision: str
    oracle_test_patch_identity: str
    fail_to_pass: tuple[str, ...]
    pass_to_pass: tuple[str, ...]
    harness_commit_or_digest: str
    verification_configuration_digest: str
    verifier_environment_image_digest: str | None = None
    verifier_identity: str | None = None
    schema_version: str = "oma7.verification-context/v1"

    def is_valid(self) -> bool:
        return all(
            (
                self.dataset_revision,
                self.oracle_test_patch_identity,
                self.harness_commit_or_digest,
                self.verification_configuration_digest,
            )
        )

    def identity(self) -> str:
        if not self.is_valid():
            raise ValueError("verification context requires mandatory fields")
        return _digest_payload(self)


@dataclass(frozen=True)
class ScopePolicyIdentity:
    allowed_scope_path_policy: tuple[str, ...]
    protected_semantic_roles: tuple[str, ...]
    explicit_sensitive_change_authorizations: tuple[str, ...]
    scope_budget: str
    task_specific_exceptions: tuple[str, ...]
    rule_schema_version: str

    def identity(self) -> str:
        return _digest_payload(self)


@dataclass(frozen=True)
class ProvenanceAnchorIdentity:
    anchor_type: str
    immutable_anchor_identifier_digest: str
    provenance_root: str
    event_count: int | None = None
    schema_information: str | None = None

    def is_valid(self) -> bool:
        return bool(self.anchor_type and self.immutable_anchor_identifier_digest and self.provenance_root)

    def identity(self) -> str:
        if not self.is_valid():
            raise ValueError("provenance anchor requires mandatory fields")
        return _digest_payload(self)


@dataclass(frozen=True)
class SnapshotIdentity:
    root: str
    git_status: str
    git_index: str


MaterializationSnapshotIdentity = SnapshotIdentity


@dataclass(frozen=True)
class EvidenceApplicability:
    subject_identity: SubjectIdentity | None
    materialization_identity: MaterializationIdentity | None
    execution_context_identity: ExecutionContextIdentity | None
    verification_context_identity: VerificationContextIdentity | None
    scope_policy_identity: ScopePolicyIdentity | None
    provenance_anchor_identity: ProvenanceAnchorIdentity | None
    result: ResultStatus

    @property
    def authorizes_acceptance(self) -> bool:
        return (
            self.result == ResultStatus.PASS
            and self.subject_identity is not None
            and self.materialization_identity is not None
            and self.execution_context_identity is not None
            and self.verification_context_identity is not None
            and self.scope_policy_identity is not None
            and self.provenance_anchor_identity is not None
        )

    @property
    def is_applicable(self) -> bool:
        return self.authorizes_acceptance


@dataclass(frozen=True)
class Evidence:
    subject_identity: SubjectIdentity | None
    materialization_identity: MaterializationIdentity | None
    execution_context_identity: ExecutionContextIdentity | None
    verification_context_identity: VerificationContextIdentity | None
    scope_policy_identity: ScopePolicyIdentity | None
    provenance_anchor_identity: ProvenanceAnchorIdentity | None
    result: ResultStatus
    schema_version: str = SCHEMA_VERSION_SUPPORTED
    verifier_id: str | None = None
    run_id: str | None = None
    cost_ledger_head: str | None = None
    cost_ledger_event_count: int | None = None
    human_intervention_summary: str | None = None
    predicate: dict[str, Any] = field(default_factory=dict)

    def is_valid_schema(self) -> bool:
        return self.schema_version == SCHEMA_VERSION_SUPPORTED

    def identity(self) -> str:
        if not self.is_valid_schema():
            raise ValueError(f"unsupported schema: {self.schema_version}")
        if any(
            identity is None
            for identity in (
                self.subject_identity,
                self.materialization_identity,
                self.execution_context_identity,
                self.verification_context_identity,
                self.scope_policy_identity,
                self.provenance_anchor_identity,
            )
        ):
            raise ValueError("missing mandatory evidence identities")
        return _digest_payload(self)


@dataclass(frozen=True)
class Observation:
    evidence: Evidence
    tests_status: dict[str, ResultStatus]
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def result(self) -> ResultStatus:
        return self.evidence.result
