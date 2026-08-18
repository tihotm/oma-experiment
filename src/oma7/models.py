from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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


@dataclass(frozen=True)
class SubjectIdentity:
    git_tree: str
    git_commit: str | None = None
    path: str = "."


@dataclass(frozen=True)
class VerificationContextIdentity:
    dataset_revision: str
    test_patch_oracle: str
    fail_to_pass: tuple[str, ...]
    pass_to_pass: tuple[str, ...]
    harness_commit: str
    verification_config: str
    environment_image: str | None = None


@dataclass(frozen=True)
class SnapshotIdentity:
    root: str
    git_status: str
    git_index: str


@dataclass(frozen=True)
class EvidenceApplicability:
    same_subject_identity: bool
    same_verification_context_identity: bool
    result: ResultStatus

    @property
    def authorizes_acceptance(self) -> bool:
        return (
            self.same_subject_identity
            and self.same_verification_context_identity
            and self.result == ResultStatus.PASS
        )


@dataclass(frozen=True)
class Evidence:
    subject_identity: SubjectIdentity
    verification_context_identity: VerificationContextIdentity
    result: ResultStatus
    predicate: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    subject_identity: SubjectIdentity
    verification_context_identity: VerificationContextIdentity
    result: ResultStatus
    tests_status: dict[str, ResultStatus]
    raw: dict[str, Any] = field(default_factory=dict)
