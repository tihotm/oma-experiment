from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .control_plane import (
    ControlPolicyIdentity,
    RetryBudget,
    SupervisorControlRecord,
    create_control_record,
    control_policy_identity_from_policy,
)
from .models import (
    ExecutionContextIdentity,
    MaterializationIdentity,
    MissionIdentity,
    ScopePolicyIdentity,
    SubjectIdentity,
    VerificationContextIdentity,
    compute_mission_identity,
)
from .preflight import (
    DEFAULT_RUNTIME_PINS,
    ProductionExecutionPlan,
    ProductionPreflightConfig,
    ProductionPreflightResult,
    RuntimePins,
    execution_context_identity_from_pins,
    make_dry_run_plan,
    run_production_preflight,
)
from .git_identity import compute_git_tree_identity


DEFAULT_HARNESS_BINDING_IDENTITY = "oma7-harness:release-candidate"
DEFAULT_SCOPE_BUDGET = "mvp-first-real-g0"
DEFAULT_VERIFICATION_COMMAND = "python -m unittest discover -s tests -v"


@dataclass(frozen=True)
class FirstRealMissionSpec:
    workspace: Path
    subject_identity: SubjectIdentity
    materialization_identity: MaterializationIdentity
    execution_context_identity: ExecutionContextIdentity
    verification_context_identity: VerificationContextIdentity
    scope_policy_identity: ScopePolicyIdentity
    mission_identity: MissionIdentity
    control_policy_identity: ControlPolicyIdentity
    retry_budget: RetryBudget
    harness_binding_identity: str = DEFAULT_HARNESS_BINDING_IDENTITY


@dataclass(frozen=True)
class ReleaseCandidateReadiness:
    workspace: str
    harness_validation_ok: bool
    docker_runtime_ready: bool
    pinned_runtime_ready: bool
    auth_ready: bool
    mission_plan_ready: bool
    production_preflight: str
    attempt_created: bool
    retry_budget_consumed: bool
    real_codex_exec: int
    execution_context_id: str
    mission_id: str
    plan_execution_context_id: str | None
    plan_blocked_reasons: tuple[str, ...]
    control_record_id: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["workspace"] = str(self.workspace)
        return data


def _digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _canonical_scope_policy() -> ScopePolicyIdentity:
    return ScopePolicyIdentity(
        allowed_scope_path_policy=("src/**", "tests/**", "docs/**", "scripts/**"),
        protected_semantic_roles=("oracle", "provenance", "verification"),
        explicit_sensitive_change_authorizations=(),
        scope_budget=DEFAULT_SCOPE_BUDGET,
        task_specific_exceptions=(),
        rule_schema_version="oma7.scope-policy/v1",
    )


def _canonical_verification_context(*, workspace: Path, execution_context_identity: ExecutionContextIdentity) -> VerificationContextIdentity:
    repo_digest = compute_git_tree_identity(workspace)
    return VerificationContextIdentity(
        dataset_revision=repo_digest,
        oracle_test_patch_identity=_digest(DEFAULT_VERIFICATION_COMMAND),
        fail_to_pass=(),
        pass_to_pass=(),
        harness_commit_or_digest=repo_digest,
        verification_configuration_digest=_digest(DEFAULT_VERIFICATION_COMMAND),
        verifier_environment_image_digest=execution_context_identity.environment_container_image_digest,
        verifier_identity="oma7-first-real-g0-verifier",
    )


def build_first_real_mission_spec(workspace: Path, pins: RuntimePins) -> FirstRealMissionSpec:
    subject = SubjectIdentity(
        git_tree=compute_git_tree_identity(workspace),
        git_commit=None,
        path=".",
    )
    materialization = MaterializationIdentity(
        subject_identity=subject,
        canonical_root_descriptor="git:root",
        worktree_reference_identity=str(workspace.resolve()),
    )
    execution_context = execution_context_identity_from_pins(pins)
    scope_policy = _canonical_scope_policy()
    verification = _canonical_verification_context(workspace=workspace, execution_context_identity=execution_context)
    mission = compute_mission_identity(
        subject_identity=subject,
        materialization_identity=materialization,
        execution_context_identity=execution_context,
        scope_policy_identity=scope_policy,
        verification_context_identity=verification,
    )
    control_policy = control_policy_identity_from_policy(
        max_attempts=1,
        max_elapsed_time_seconds=1800,
        max_execution_time_per_attempt_seconds=1800,
        retryable_classifications=(),
        non_retryable_classifications=(),
        escalation_reasons=(),
    )
    return FirstRealMissionSpec(
        workspace=workspace,
        subject_identity=subject,
        materialization_identity=materialization,
        execution_context_identity=execution_context,
        verification_context_identity=verification,
        scope_policy_identity=scope_policy,
        mission_identity=mission,
        control_policy_identity=control_policy,
        retry_budget=RetryBudget(
            max_attempts=1,
            max_elapsed_time_seconds=1800,
            max_execution_time_per_attempt_seconds=1800,
        ),
    )


def build_release_candidate_control_record(spec: FirstRealMissionSpec) -> SupervisorControlRecord:
    return create_control_record(
        run_id=spec.mission_identity.identity(),
        budget=spec.retry_budget,
        mission_identity=spec.mission_identity,
        control_policy_identity=spec.control_policy_identity,
        harness_binding_identity=spec.harness_binding_identity,
        subject_identity=spec.subject_identity,
        execution_context_identity=spec.execution_context_identity,
        verification_context_identity=spec.verification_context_identity,
        scope_policy_identity=spec.scope_policy_identity,
    )


def build_release_candidate_plan(spec: FirstRealMissionSpec) -> ProductionExecutionPlan:
    record = build_release_candidate_control_record(spec)
    return make_dry_run_plan(
        ProductionPreflightConfig(
            workspace=spec.workspace,
            pins=RuntimePins(
                codex_sha256=spec.execution_context_identity.codex_binary_digest,
                codex_version=spec.execution_context_identity.codex_version,
                model=spec.execution_context_identity.model,
                reasoning_level=spec.execution_context_identity.reasoning_level,
                harness_commit_or_digest=spec.execution_context_identity.harness_commit_or_digest,
                harness_configuration_digest=spec.execution_context_identity.harness_configuration_digest,
                dataset_revision=spec.execution_context_identity.dataset_revision,
                dependency_lock_digest=spec.execution_context_identity.dependency_lock_digest,
                container_image_digest=spec.execution_context_identity.environment_container_image_digest,
                toolchain_identity=spec.execution_context_identity.toolchain_identity,
            ),
            control_record=record,
        )
    )


def build_release_candidate_readiness(
    *,
    workspace: Path,
    pins: RuntimePins,
    harness_validation_ok: bool,
    docker_runtime_ready: bool,
    pinned_runtime_ready: bool,
    auth_ready: bool,
) -> ReleaseCandidateReadiness:
    spec = build_first_real_mission_spec(workspace, pins)
    control_record = build_release_candidate_control_record(spec)
    plan = build_release_candidate_plan(spec)
    preflight_result = run_production_preflight(
        ProductionPreflightConfig(workspace=workspace, pins=pins, control_record=control_record)
    )
    return ReleaseCandidateReadiness(
        workspace=str(workspace),
        harness_validation_ok=harness_validation_ok,
        docker_runtime_ready=docker_runtime_ready,
        pinned_runtime_ready=pinned_runtime_ready,
        auth_ready=auth_ready,
        mission_plan_ready=plan.result == ProductionPreflightResult.READY,
        production_preflight=preflight_result.value,
        attempt_created=False,
        retry_budget_consumed=False,
        real_codex_exec=0,
        execution_context_id=spec.execution_context_identity.identity(),
        mission_id=spec.mission_identity.identity(),
        plan_execution_context_id=plan.execution_context_id,
        plan_blocked_reasons=plan.blocked_reasons,
        control_record_id=control_record.identity(),
    )


def build_default_release_candidate_readiness(
    *,
    workspace: Path,
    harness_validation_ok: bool,
    docker_runtime_ready: bool,
    pinned_runtime_ready: bool,
    auth_ready: bool,
) -> ReleaseCandidateReadiness:
    return build_release_candidate_readiness(
        workspace=workspace,
        pins=DEFAULT_RUNTIME_PINS,
        harness_validation_ok=harness_validation_ok,
        docker_runtime_ready=docker_runtime_ready,
        pinned_runtime_ready=pinned_runtime_ready,
        auth_ready=auth_ready,
    )
