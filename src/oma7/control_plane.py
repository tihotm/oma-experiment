from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import os
from hashlib import sha256
from pathlib import Path
from time import monotonic, time
from typing import Any

from .docker_lifecycle import (
    OMA7_RUN_ID_LABEL,
    docker_create,
    docker_exec,
    docker_executable,
    docker_inspect_container,
    docker_list_containers,
    docker_remove,
    docker_start,
    docker_stop,
    inspect_image,
)
from .lifecycle import (
    AcceptanceDecision,
    ControlledLifecycleObservation,
    LifecycleState,
    evaluate_acceptance,
    finalize_durable_done,
    publish_atomic_evidence,
    write_durable_run_record,
    DurableRunRecord,
    RunIdentity,
    ResumeClassification,
    load_durable_run_record,
    load_published_evidence,
    SUPPORTED_RUN_RECORD_SCHEMA,
    evidence_publication_payload,
)
from .models import (
    Evidence,
    ExecutionContextIdentity,
    MissionIdentity,
    MaterializationIdentity,
    ProvenanceAnchorIdentity,
    ResultStatus,
    ScopePolicyIdentity,
    SubjectIdentity,
    VerificationContextIdentity,
)
from .scope import ScopeDecision, ScopeEvaluation


class SupervisorState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"
    ACCEPTED = "ACCEPTED"
    ESCALATION_REQUIRED = "ESCALATION_REQUIRED"


class FailureClassification(str, Enum):
    RETRYABLE = "RETRYABLE"
    NON_RETRYABLE = "NON_RETRYABLE"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    UNKNOWN_FAIL_CLOSED = "UNKNOWN_FAIL_CLOSED"


class EscalationReason(str, Enum):
    REPEATED_RETRYABLE_FAILURE = "REPEATED_RETRYABLE_FAILURE"
    AMBIGUOUS_STATE = "AMBIGUOUS_STATE"
    HUMAN_ACTION_REQUIRED = "HUMAN_ACTION_REQUIRED"
    BUDGET_OVERRIDE_REQUIRED = "BUDGET_OVERRIDE_REQUIRED"
    POLICY_BOUNDARY = "POLICY_BOUNDARY"
    MISSION_AMBIGUITY = "MISSION_AMBIGUITY"


@dataclass(frozen=True)
class RetryBudget:
    max_attempts: int
    max_elapsed_time_seconds: float
    max_execution_time_per_attempt_seconds: float
    max_cost_units: int | None = None


@dataclass(frozen=True)
class ControlPolicyIdentity:
    max_attempts: int
    max_elapsed_time_seconds: float
    max_execution_time_per_attempt_seconds: float
    retryable_classifications: tuple[FailureClassification, ...]
    non_retryable_classifications: tuple[FailureClassification, ...]
    escalation_reasons: tuple[EscalationReason, ...]
    pointless_identical_retry_blocked: bool = True

    def identity(self) -> str:
        return sha256(json.dumps(_canonical(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def control_policy_identity_from_policy(
    *,
    max_attempts: int,
    max_elapsed_time_seconds: float,
    max_execution_time_per_attempt_seconds: float,
    retryable_classifications: tuple[FailureClassification, ...],
    non_retryable_classifications: tuple[FailureClassification, ...],
    escalation_reasons: tuple[EscalationReason, ...],
    pointless_identical_retry_blocked: bool = True,
) -> ControlPolicyIdentity:
    return ControlPolicyIdentity(
        max_attempts=max_attempts,
        max_elapsed_time_seconds=max_elapsed_time_seconds,
        max_execution_time_per_attempt_seconds=max_execution_time_per_attempt_seconds,
        retryable_classifications=retryable_classifications,
        non_retryable_classifications=non_retryable_classifications,
        escalation_reasons=escalation_reasons,
        pointless_identical_retry_blocked=pointless_identical_retry_blocked,
    )


@dataclass(frozen=True)
class BudgetState:
    attempts_used: int = 0
    elapsed_seconds: float = 0.0
    cost_used: int = 0

    def remaining_attempts(self, budget: RetryBudget) -> int:
        return max(0, budget.max_attempts - self.attempts_used)

    def exhausted(self, budget: RetryBudget) -> bool:
        return self.attempts_used >= budget.max_attempts or self.elapsed_seconds >= budget.max_elapsed_time_seconds


@dataclass(frozen=True)
class AttemptIdentity:
    run_id: str
    attempt_id: str
    parent_attempt_id: str | None = None
    superseded_attempt_id: str | None = None
    execution_context_identity: ExecutionContextIdentity | None = None
    subject_identity: SubjectIdentity | None = None
    start_time: float | None = None
    end_time: float | None = None
    termination_reason: str | None = None
    evidence_reference: str | None = None

    def identity(self) -> str:
        payload = json.dumps(_canonical(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AttemptRecord:
    attempt_identity: AttemptIdentity
    state: SupervisorState
    failure_classification: FailureClassification | None = None
    evidence_reference: str | None = None
    verifier_evidence_reference: str | None = None
    current: bool = False


@dataclass(frozen=True)
class SupervisorControlRecord:
    schema_version: str
    mission_id: str
    run_id: str
    state: SupervisorState
    budget: RetryBudget
    budget_state: BudgetState
    current_attempt_id: str | None
    # Durable identity bindings — set once at creation, validated on reload.
    # mission_id is the hash of MissionIdentity (pre-execution).
    # control_policy_id is the hash of ControlPolicyIdentity.
    # scope_policy_id is the hash of ScopePolicyIdentity.
    control_policy_id: str | None = None
    scope_policy_id: str | None = None
    attempts: tuple[AttemptRecord, ...] = ()
    subject_identity: SubjectIdentity | None = None
    mission_identity: MissionIdentity | None = None
    control_policy_identity: ControlPolicyIdentity | None = None
    harness_binding_identity: str | None = None
    execution_context_identity: ExecutionContextIdentity | None = None
    verification_context_identity: VerificationContextIdentity | None = None
    scope_policy_identity: ScopePolicyIdentity | None = None
    provenance_anchor_identity: ProvenanceAnchorIdentity | None = None
    latest_transition: str | None = None
    escalation_reason: EscalationReason | None = None
    failure_classification: FailureClassification | None = None
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)

    def identity(self) -> str:
        payload = _canonical(self)
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    @property
    def current_attempts(self) -> tuple[AttemptRecord, ...]:
        return tuple(item for item in self.attempts if item.current)

    def with_attempt(self, attempt: AttemptRecord, *, current: bool = True) -> SupervisorControlRecord:
        updated_attempts = tuple(
            AttemptRecord(
                attempt_identity=item.attempt_identity,
                state=item.state,
                failure_classification=item.failure_classification,
                evidence_reference=item.evidence_reference,
                verifier_evidence_reference=item.verifier_evidence_reference,
                current=False if item.attempt_identity.attempt_id == attempt.attempt_identity.attempt_id else item.current,
            )
            for item in self.attempts
        )
        new_attempt = AttemptRecord(
            attempt_identity=attempt.attempt_identity,
            state=attempt.state,
            failure_classification=attempt.failure_classification,
            evidence_reference=attempt.evidence_reference,
            verifier_evidence_reference=attempt.verifier_evidence_reference,
            current=current,
        )
        return SupervisorControlRecord(
            schema_version=self.schema_version,
            mission_id=self.mission_id,
            run_id=self.run_id,
            state=self.state,
            budget=self.budget,
            budget_state=self.budget_state,
            current_attempt_id=attempt.attempt_identity.attempt_id if current else self.current_attempt_id,
            control_policy_id=self.control_policy_id,
            scope_policy_id=self.scope_policy_id,
            attempts=updated_attempts + (new_attempt,),
            subject_identity=self.subject_identity,
            mission_identity=self.mission_identity,
            control_policy_identity=self.control_policy_identity,
            harness_binding_identity=self.harness_binding_identity,
            execution_context_identity=self.execution_context_identity,
            verification_context_identity=self.verification_context_identity,
            scope_policy_identity=self.scope_policy_identity,
            provenance_anchor_identity=self.provenance_anchor_identity,
            latest_transition=self.latest_transition,
            escalation_reason=self.escalation_reason,
            failure_classification=self.failure_classification,
            created_at=self.created_at,
            updated_at=time(),
        )


SUPPORTED_CONTROL_RECORD_SCHEMA = "oma7.supervisor-control/v1"


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
        return {str(k): _canonical(v) for k, v in sorted(value.items())}
    if hasattr(value, "__dataclass_fields__"):
        return {k: _canonical(getattr(value, k)) for k in sorted(value.__dataclass_fields__) if getattr(value, k) is not None}
    raise TypeError(type(value))


def control_record_payload(record: SupervisorControlRecord) -> dict[str, Any]:
    return _canonical(record)


def _load_subject_identity(payload: dict[str, Any] | None) -> SubjectIdentity | None:
    if payload is None:
        return None
    return SubjectIdentity(
        git_tree=payload["git_tree"],
        git_commit=payload.get("git_commit"),
        path=payload.get("path", "."),
        schema_version=payload.get("schema_version", "oma7.subject/v1"),
    )


def _load_materialization_identity(payload: dict[str, Any] | None) -> MaterializationIdentity | None:
    if payload is None:
        return None
    subject = _load_subject_identity(payload["subject_identity"])
    if subject is None:
        return None
    return MaterializationIdentity(
        subject_identity=subject,
        canonical_root_descriptor=payload["canonical_root_descriptor"],
        symlink_topology=tuple(tuple(item) for item in payload.get("symlink_topology", ())),
        hardlink_topology=tuple(tuple(item) for item in payload.get("hardlink_topology", ())),
        worktree_reference_identity=payload.get("worktree_reference_identity"),
        mounted_reference_artifact_identities=tuple(payload.get("mounted_reference_artifact_identities", ())),
        cache_manifest_digest=payload.get("cache_manifest_digest"),
        schema_version=payload.get("schema_version", "oma7.materialization/v1"),
    )


def _load_execution_context_identity(payload: dict[str, Any] | None) -> ExecutionContextIdentity | None:
    if payload is None:
        return None
    return ExecutionContextIdentity(
        environment_container_image_digest=payload["environment_container_image_digest"],
        codex_binary_digest=payload["codex_binary_digest"],
        codex_version=payload["codex_version"],
        model=payload["model"],
        reasoning_level=payload["reasoning_level"],
        harness_commit_or_digest=payload["harness_commit_or_digest"],
        harness_configuration_digest=payload["harness_configuration_digest"],
        dependency_lock_digest=payload["dependency_lock_digest"],
        dataset_revision=payload["dataset_revision"],
        toolchain_identity=payload["toolchain_identity"],
        schema_version=payload.get("schema_version", "oma7.execution-context/v1"),
    )


def _load_scope_policy_identity(payload: dict[str, Any] | None) -> ScopePolicyIdentity | None:
    if payload is None:
        return None
    return ScopePolicyIdentity(
        allowed_scope_path_policy=tuple(payload["allowed_scope_path_policy"]),
        protected_semantic_roles=tuple(payload["protected_semantic_roles"]),
        explicit_sensitive_change_authorizations=tuple(payload["explicit_sensitive_change_authorizations"]),
        scope_budget=payload["scope_budget"],
        task_specific_exceptions=tuple(payload["task_specific_exceptions"]),
        rule_schema_version=payload["rule_schema_version"],
    )


def _load_mission_identity(payload: dict[str, Any] | None) -> MissionIdentity | None:
    if payload is None:
        return None
    subject = _load_subject_identity(payload["subject_identity"])
    materialization = _load_materialization_identity(payload["materialization_identity"])
    execution = _load_execution_context_identity(payload["execution_context_identity"])
    scope_policy = _load_scope_policy_identity(payload["scope_policy_identity"])
    if subject is None or materialization is None or execution is None or scope_policy is None:
        return None
    verification = payload.get("verification_context_identity")
    provenance = payload.get("provenance_anchor_identity")
    return MissionIdentity(
        subject_identity=subject,
        materialization_identity=materialization,
        execution_context_identity=execution,
        scope_policy_identity=scope_policy,
        verification_context_identity=None if verification is None else VerificationContextIdentity(
            dataset_revision=verification["dataset_revision"],
            oracle_test_patch_identity=verification["oracle_test_patch_identity"],
            fail_to_pass=tuple(verification.get("fail_to_pass", ())),
            pass_to_pass=tuple(verification.get("pass_to_pass", ())),
            harness_commit_or_digest=verification["harness_commit_or_digest"],
            verification_configuration_digest=verification["verification_configuration_digest"],
            verifier_environment_image_digest=verification.get("verifier_environment_image_digest"),
            verifier_identity=verification.get("verifier_identity"),
            schema_version=verification.get("schema_version", "oma7.verification-context/v1"),
        ),
        provenance_anchor_identity=None if provenance is None else ProvenanceAnchorIdentity(
            anchor_type=provenance["anchor_type"],
            immutable_anchor_identifier_digest=provenance["immutable_anchor_identifier_digest"],
            provenance_root=provenance["provenance_root"],
            event_count=provenance.get("event_count"),
            schema_information=provenance.get("schema_information"),
        ),
        schema_version=payload.get("schema_version", "oma7.mission/v1"),
    )


def _load_control_policy_identity(payload: dict[str, Any] | None) -> ControlPolicyIdentity | None:
    if payload is None:
        return None
    return ControlPolicyIdentity(
        max_attempts=payload["max_attempts"],
        max_elapsed_time_seconds=payload["max_elapsed_time_seconds"],
        max_execution_time_per_attempt_seconds=payload["max_execution_time_per_attempt_seconds"],
        retryable_classifications=tuple(FailureClassification(item) for item in payload["retryable_classifications"]),
        non_retryable_classifications=tuple(FailureClassification(item) for item in payload["non_retryable_classifications"]),
        escalation_reasons=tuple(EscalationReason(item) for item in payload["escalation_reasons"]),
        pointless_identical_retry_blocked=payload.get("pointless_identical_retry_blocked", True),
    )


def write_control_record(path: str | Path, record: SupervisorControlRecord) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    payload = control_record_payload(record)
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(target)
    return target


def load_control_record(path: str | Path) -> SupervisorControlRecord | None:
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != SUPPORTED_CONTROL_RECORD_SCHEMA:
        return None
    try:
        record = SupervisorControlRecord(
            schema_version=payload["schema_version"],
            mission_id=payload["mission_id"],
            run_id=payload["run_id"],
            state=SupervisorState(payload["state"]),
            budget=RetryBudget(**payload["budget"]),
            budget_state=BudgetState(**payload["budget_state"]),
            current_attempt_id=payload.get("current_attempt_id"),
            # Durable hash bindings — strings, not objects.
            control_policy_id=payload.get("control_policy_id"),
            scope_policy_id=payload.get("scope_policy_id"),
            attempts=tuple(
                AttemptRecord(
                    attempt_identity=AttemptIdentity(
                        run_id=item["attempt_identity"]["run_id"],
                        attempt_id=item["attempt_identity"]["attempt_id"],
                        parent_attempt_id=item["attempt_identity"].get("parent_attempt_id"),
                        superseded_attempt_id=item["attempt_identity"].get("superseded_attempt_id"),
                        execution_context_identity=None,
                        subject_identity=None,
                        start_time=item["attempt_identity"].get("start_time"),
                        end_time=item["attempt_identity"].get("end_time"),
                        termination_reason=item["attempt_identity"].get("termination_reason"),
                        evidence_reference=item["attempt_identity"].get("evidence_reference"),
                    ),
                    state=SupervisorState(item["state"]),
                    failure_classification=FailureClassification(item["failure_classification"]) if item.get("failure_classification") else None,
                    evidence_reference=item.get("evidence_reference"),
                    verifier_evidence_reference=item.get("verifier_evidence_reference"),
                    current=item.get("current", False),
                )
                for item in payload.get("attempts", [])
            ),
            subject_identity=_load_subject_identity(payload.get("subject_identity")),
            mission_identity=_load_mission_identity(payload.get("mission_identity")),
            control_policy_identity=_load_control_policy_identity(payload.get("control_policy_identity")),
            harness_binding_identity=payload.get("harness_binding_identity"),
            execution_context_identity=_load_execution_context_identity(payload.get("execution_context_identity")),
            verification_context_identity=None if payload.get("verification_context_identity") is None else VerificationContextIdentity(
                dataset_revision=payload["verification_context_identity"]["dataset_revision"],
                oracle_test_patch_identity=payload["verification_context_identity"]["oracle_test_patch_identity"],
                fail_to_pass=tuple(payload["verification_context_identity"].get("fail_to_pass", ())),
                pass_to_pass=tuple(payload["verification_context_identity"].get("pass_to_pass", ())),
                harness_commit_or_digest=payload["verification_context_identity"]["harness_commit_or_digest"],
                verification_configuration_digest=payload["verification_context_identity"]["verification_configuration_digest"],
                verifier_environment_image_digest=payload["verification_context_identity"].get("verifier_environment_image_digest"),
                verifier_identity=payload["verification_context_identity"].get("verifier_identity"),
            ),
            scope_policy_identity=_load_scope_policy_identity(payload.get("scope_policy_identity")),
            provenance_anchor_identity=None if payload.get("provenance_anchor_identity") is None else ProvenanceAnchorIdentity(
                anchor_type=payload["provenance_anchor_identity"]["anchor_type"],
                immutable_anchor_identifier_digest=payload["provenance_anchor_identity"]["immutable_anchor_identifier_digest"],
                provenance_root=payload["provenance_anchor_identity"]["provenance_root"],
                event_count=payload["provenance_anchor_identity"].get("event_count"),
                schema_information=payload["provenance_anchor_identity"].get("schema_information"),
            ),
            latest_transition=payload.get("latest_transition"),
            escalation_reason=EscalationReason(payload["escalation_reason"]) if payload.get("escalation_reason") else None,
            failure_classification=FailureClassification(payload["failure_classification"]) if payload.get("failure_classification") else None,
            created_at=payload.get("created_at", 0.0),
            updated_at=payload.get("updated_at", 0.0),
        )
        if not validate_control_record(record):
            return None
        return record
    except Exception:
        return None


def validate_control_record(record: SupervisorControlRecord) -> bool:
    if record.schema_version != SUPPORTED_CONTROL_RECORD_SCHEMA:
        return False
    if not record.mission_id or not record.run_id:
        return False
    if record.budget.max_attempts < 0:
        return False
    if record.budget.max_elapsed_time_seconds < 0 or record.budget.max_execution_time_per_attempt_seconds < 0:
        return False
    if record.budget_state.attempts_used < 0 or record.budget_state.elapsed_seconds < 0 or record.budget_state.cost_used < 0:
        return False
    if record.current_attempt_id is None and record.state in {SupervisorState.RUNNING, SupervisorState.VERIFYING}:
        return False
    if len(record.current_attempts) > 1:
        return False
    current_attempt_ids = {item.attempt_identity.attempt_id for item in record.current_attempts}
    if record.current_attempt_id is not None and record.current_attempt_id not in current_attempt_ids:
        return False
    if len({item.attempt_identity.attempt_id for item in record.attempts}) != len(record.attempts):
        return False
    if record.state == SupervisorState.ACCEPTED and record.failure_classification is not None:
        return False
    # Durable binding consistency: if mission_identity object is present, its
    # hash must exactly match the persisted mission_id string.  A mismatch
    # means the record was modified after creation — reject fail-closed.
    if record.mission_identity is not None:
        try:
            if record.mission_identity.identity() != record.mission_id:
                return False
        except Exception:
            return False
        # When a mission_identity is bound, control/scope policy hashes must
        # also be present and consistent.
        if not record.control_policy_id or not record.scope_policy_id:
            return False
        if record.control_policy_identity is not None:
            try:
                if record.control_policy_identity.identity() != record.control_policy_id:
                    return False
            except Exception:
                return False
        if record.scope_policy_identity is not None:
            try:
                if record.scope_policy_identity.identity() != record.scope_policy_id:
                    return False
            except Exception:
                return False
    return True



def preflight_ready(record: SupervisorControlRecord) -> bool:
    if not validate_control_record(record):
        return False
    if record.mission_identity is None or record.control_policy_identity is None or not record.harness_binding_identity:
        return False
    if not record.mission_identity.is_valid():
        return False
    if record.subject_identity is not None and record.mission_identity.subject_identity != record.subject_identity:
        return False
    if record.execution_context_identity is not None and record.mission_identity.execution_context_identity != record.execution_context_identity:
        return False
    if record.scope_policy_identity is not None and record.mission_identity.scope_policy_identity != record.scope_policy_identity:
        return False
    return True


def classify_failure(*, exit_code: int | None = None, timed_out: bool = False, scope_violation: bool = False, provenance_mismatch: bool = False, verifier_crash: bool = False, malformed_output: bool = False, auth_missing: bool = False, invalid_pin: bool = False, budget_exhausted: bool = False, infrastructure_failure: bool = False) -> FailureClassification:
    if budget_exhausted:
        return FailureClassification.BUDGET_EXHAUSTED
    if scope_violation or provenance_mismatch:
        return FailureClassification.POLICY_VIOLATION
    if auth_missing or invalid_pin:
        return FailureClassification.NON_RETRYABLE
    if verifier_crash or malformed_output:
        return FailureClassification.VERIFICATION_FAILURE
    if infrastructure_failure or timed_out:
        return FailureClassification.INFRASTRUCTURE_FAILURE
    if exit_code not in (None, 0):
        return FailureClassification.NON_RETRYABLE
    return FailureClassification.UNKNOWN_FAIL_CLOSED


def can_retry(classification: FailureClassification, budget: RetryBudget, state: BudgetState, *, progress_exists: bool, context_changed: bool, attempt_number: int) -> bool:
    if state.exhausted(budget):
        return False
    if classification in {FailureClassification.POLICY_VIOLATION, FailureClassification.BUDGET_EXHAUSTED, FailureClassification.NON_RETRYABLE, FailureClassification.UNKNOWN_FAIL_CLOSED}:
        return False
    if classification == FailureClassification.VERIFICATION_FAILURE:
        return False
    if classification == FailureClassification.INFRASTRUCTURE_FAILURE:
        return progress_exists or context_changed or attempt_number == 0
    return False


def transition_allowed(from_state: SupervisorState, to_state: SupervisorState, *, has_new_attempt: bool = False, has_verification_result: bool = False, has_valid_evidence: bool = False) -> bool:
    rules = {
        SupervisorState.PENDING: {SupervisorState.RUNNING, SupervisorState.ESCALATION_REQUIRED, SupervisorState.TERMINAL_FAILURE},
        SupervisorState.RUNNING: {SupervisorState.VERIFYING, SupervisorState.RETRYABLE_FAILURE, SupervisorState.TERMINAL_FAILURE, SupervisorState.ESCALATION_REQUIRED},
        SupervisorState.VERIFYING: {SupervisorState.ACCEPTED, SupervisorState.RETRYABLE_FAILURE, SupervisorState.TERMINAL_FAILURE, SupervisorState.ESCALATION_REQUIRED},
        SupervisorState.RETRYABLE_FAILURE: {SupervisorState.RUNNING, SupervisorState.ESCALATION_REQUIRED, SupervisorState.TERMINAL_FAILURE},
        SupervisorState.TERMINAL_FAILURE: set(),
        SupervisorState.ACCEPTED: set(),
        SupervisorState.ESCALATION_REQUIRED: set(),
    }
    if to_state not in rules.get(from_state, set()):
        return False
    if from_state == SupervisorState.VERIFYING and to_state == SupervisorState.ACCEPTED:
        return has_verification_result and has_valid_evidence
    if from_state == SupervisorState.RETRYABLE_FAILURE and to_state == SupervisorState.RUNNING:
        return has_new_attempt
    return True


def new_attempt_identity(run_id: str, attempt_number: int, *, parent_attempt_id: str | None = None, superseded_attempt_id: str | None = None, execution_context_identity: ExecutionContextIdentity | None = None, subject_identity: SubjectIdentity | None = None) -> AttemptIdentity:
    attempt_id = f"{run_id}:{attempt_number}"
    return AttemptIdentity(
        run_id=run_id,
        attempt_id=attempt_id,
        parent_attempt_id=parent_attempt_id,
        superseded_attempt_id=superseded_attempt_id,
        execution_context_identity=execution_context_identity,
        subject_identity=subject_identity,
    )


def record_attempt(attempt: AttemptIdentity, state: SupervisorState, *, failure_classification: FailureClassification | None = None, evidence_reference: str | None = None, verifier_evidence_reference: str | None = None) -> AttemptRecord:
    return AttemptRecord(attempt_identity=attempt, state=state, failure_classification=failure_classification, evidence_reference=evidence_reference, verifier_evidence_reference=verifier_evidence_reference)


def supervisor_state_from_record(record: SupervisorControlRecord) -> SupervisorState:
    if record.state == SupervisorState.VERIFYING and record.current_attempt_id is None:
        return SupervisorState.ESCALATION_REQUIRED
    return record.state


def create_control_record(
    *,
    run_id: str,
    budget: RetryBudget,
    mission_identity: MissionIdentity,
    control_policy_identity: ControlPolicyIdentity,
    harness_binding_identity: str,
    subject_identity: SubjectIdentity | None = None,
    execution_context_identity: ExecutionContextIdentity | None = None,
    verification_context_identity: VerificationContextIdentity | None = None,
    scope_policy_identity: ScopePolicyIdentity | None = None,
    provenance_anchor_identity: ProvenanceAnchorIdentity | None = None,
) -> SupervisorControlRecord:
    """Create a new control record with durably bound mission/policy identities.

    mission_id is derived deterministically from the MissionIdentity object so
    that callers cannot accidentally pass an arbitrary string.  The
    control_policy_id and scope_policy_id hashes are also computed and stored so
    that validate_control_record can verify consistency on every reload.

    All required identity objects must be valid; raises ValueError otherwise.
    """
    if not mission_identity.is_valid():
        raise ValueError("create_control_record: mission_identity is not valid")
    mission_id = mission_identity.identity()
    control_policy_id = control_policy_identity.identity()
    # scope_policy_id comes from the MissionIdentity's scope policy, or from the
    # separately supplied scope_policy_identity if also provided.
    scope_pi = scope_policy_identity if scope_policy_identity is not None else mission_identity.scope_policy_identity
    scope_policy_id = scope_pi.identity()
    return SupervisorControlRecord(
        schema_version=SUPPORTED_CONTROL_RECORD_SCHEMA,
        mission_id=mission_id,
        run_id=run_id,
        state=SupervisorState.PENDING,
        budget=budget,
        budget_state=BudgetState(),
        current_attempt_id=None,
        control_policy_id=control_policy_id,
        scope_policy_id=scope_policy_id,
        mission_identity=mission_identity,
        control_policy_identity=control_policy_identity,
        harness_binding_identity=harness_binding_identity,
        subject_identity=subject_identity,
        execution_context_identity=execution_context_identity,
        verification_context_identity=verification_context_identity,
        scope_policy_identity=scope_pi,
        provenance_anchor_identity=provenance_anchor_identity,
    )


def bind_control_record(
    record: SupervisorControlRecord,
    *,
    mission_identity: MissionIdentity,
    control_policy_identity: ControlPolicyIdentity,
    harness_binding_identity: str,
    subject_identity: SubjectIdentity | None = None,
    execution_context_identity: ExecutionContextIdentity | None = None,
    verification_context_identity: VerificationContextIdentity | None = None,
    scope_policy_identity: ScopePolicyIdentity | None = None,
    provenance_anchor_identity: ProvenanceAnchorIdentity | None = None,
) -> SupervisorControlRecord:
    scope_pi = scope_policy_identity if scope_policy_identity is not None else record.scope_policy_identity
    return SupervisorControlRecord(
        schema_version=record.schema_version,
        mission_id=mission_identity.identity(),
        run_id=record.run_id,
        state=record.state,
        budget=record.budget,
        budget_state=record.budget_state,
        current_attempt_id=record.current_attempt_id,
        control_policy_id=control_policy_identity.identity(),
        scope_policy_id=scope_pi.identity() if scope_pi else None,
        attempts=record.attempts,
        subject_identity=subject_identity if subject_identity is not None else record.subject_identity,
        mission_identity=mission_identity,
        control_policy_identity=control_policy_identity,
        harness_binding_identity=harness_binding_identity,
        execution_context_identity=execution_context_identity if execution_context_identity is not None else record.execution_context_identity,
        verification_context_identity=verification_context_identity if verification_context_identity is not None else record.verification_context_identity,
        scope_policy_identity=scope_policy_identity if scope_policy_identity is not None else record.scope_policy_identity,
        provenance_anchor_identity=provenance_anchor_identity if provenance_anchor_identity is not None else record.provenance_anchor_identity,
        latest_transition=record.latest_transition,
        escalation_reason=record.escalation_reason,
        failure_classification=record.failure_classification,
        created_at=record.created_at,
        updated_at=time(),
    )


def update_budget_state(state: BudgetState, *, elapsed_delta: float = 0.0, attempts_delta: int = 0, cost_delta: int = 0) -> BudgetState:
    return BudgetState(
        attempts_used=state.attempts_used + attempts_delta,
        elapsed_seconds=state.elapsed_seconds + elapsed_delta,
        cost_used=state.cost_used + cost_delta,
    )


def escalation_justified(*, repeated_retryable_failure: bool = False, ambiguous_state: bool = False, human_action_required: bool = False, budget_override_required: bool = False, policy_boundary: bool = False, mission_ambiguity: bool = False) -> bool:
    return any((repeated_retryable_failure, ambiguous_state, human_action_required, budget_override_required, policy_boundary, mission_ambiguity))


def subject_identity_from_execution(execution_context_identity: ExecutionContextIdentity, subject_identity: SubjectIdentity) -> SubjectIdentity:
    return subject_identity


def progress_is_reusable(previous: Evidence | None, current_subject: SubjectIdentity | None, current_materialization: MaterializationIdentity | None) -> bool:
    if previous is None:
        return False
    if current_subject is None or current_materialization is None:
        return False
    return previous.subject_identity == current_subject and previous.materialization_identity == current_materialization and previous.result == ResultStatus.PASS


def stale_progress_reuse_rejected(previous: Evidence | None, current_subject: SubjectIdentity | None, current_materialization: MaterializationIdentity | None) -> bool:
    return not progress_is_reusable(previous, current_subject, current_materialization)


def duplicate_execution_prevented(existing_attempts: tuple[AttemptRecord, ...], run_id: str) -> bool:
    active = [a for a in existing_attempts if a.attempt_identity.run_id == run_id and a.state == SupervisorState.RUNNING]
    return len(active) <= 1


def duplicate_acceptance_prevented(previous_acceptance: Evidence | None, replayed_evidence: Evidence | None) -> bool:
    if previous_acceptance is None or replayed_evidence is None:
        return True
    return previous_acceptance.identity() == replayed_evidence.identity()


def can_start_attempt(record: SupervisorControlRecord, *, next_attempt: AttemptIdentity, retry_reason: FailureClassification | None = None, has_changed_conditions: bool = False) -> bool:
    if record.state in {SupervisorState.ACCEPTED, SupervisorState.TERMINAL_FAILURE, SupervisorState.ESCALATION_REQUIRED}:
        return False
    if record.budget_state.exhausted(record.budget):
        return False
    if record.current_attempt_id is not None and record.state == SupervisorState.RUNNING:
        return False
    if record.current_attempt_id is not None and record.current_attempt_id == next_attempt.attempt_id:
        return False
    if retry_reason in {FailureClassification.POLICY_VIOLATION, FailureClassification.BUDGET_EXHAUSTED, FailureClassification.NON_RETRYABLE, FailureClassification.UNKNOWN_FAIL_CLOSED, FailureClassification.VERIFICATION_FAILURE} and not has_changed_conditions:
        return False
    if record.attempts:
        previous = record.attempts[-1]
        if previous.attempt_identity.execution_context_identity == next_attempt.execution_context_identity and previous.attempt_identity.subject_identity == next_attempt.subject_identity and not has_changed_conditions:
            return False
    return True


def classify_restart(
    record: SupervisorControlRecord | None,
    *,
    runtime_executor_active: bool = False,
    frozen_submission_exists: bool = False,
    verifier_complete: bool = False,
    evidence: Evidence | None = None,
) -> SupervisorState:
    if record is None:
        return SupervisorState.ESCALATION_REQUIRED
    if not validate_control_record(record):
        return SupervisorState.ESCALATION_REQUIRED
    if record.state == SupervisorState.ACCEPTED and evidence is not None:
        return SupervisorState.ACCEPTED if duplicate_acceptance_prevented(evidence, evidence) else SupervisorState.TERMINAL_FAILURE
    if record.budget_state.exhausted(record.budget):
        return SupervisorState.ESCALATION_REQUIRED
    if runtime_executor_active:
        return SupervisorState.RUNNING
    if record.state == SupervisorState.RUNNING and not frozen_submission_exists:
        return SupervisorState.RETRYABLE_FAILURE
    if frozen_submission_exists and not verifier_complete:
        if record.state in {SupervisorState.RUNNING, SupervisorState.PENDING, SupervisorState.RETRYABLE_FAILURE}:
            return SupervisorState.VERIFYING
    if record.state == SupervisorState.RUNNING and not runtime_executor_active:
        return SupervisorState.RETRYABLE_FAILURE
    if frozen_submission_exists and verifier_complete:
        return SupervisorState.VERIFYING
    return record.state


def control_record_to_payload(record: SupervisorControlRecord) -> dict[str, Any]:
    payload = _canonical(record)
    payload["schema_version"] = record.schema_version
    return payload
