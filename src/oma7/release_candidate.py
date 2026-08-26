from __future__ import annotations

from dataclasses import dataclass, asdict, field
from hashlib import sha256
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .control_plane import (
    ControlPolicyIdentity,
    AttemptIdentity,
    RetryBudget,
    SupervisorControlRecord,
    create_control_record,
    control_policy_identity_from_policy,
)
from .post_execution import PersistedExecutionArtifacts, persist_canonical_execution_artifacts
from .models import (
    ExecutionContextIdentity,
    MaterializationIdentity,
    MissionIdentity,
    Evidence,
    ResultStatus,
    ScopePolicyIdentity,
    SubjectIdentity,
    VerificationContextIdentity,
    compute_mission_identity,
)
from .preflight import (
    DEFAULT_RUNTIME_PINS,
    DEFAULT_SANDBOX_COMMAND,
    ProductionExecutionPlan,
    ProductionPreflightConfig,
    ProductionPreflightResult,
    RuntimePins,
    SandboxPreflightConfig,
    execution_context_identity_from_pins,
    make_dry_run_plan,
    run_production_preflight,
    run_sandbox_preflight,
)
from .git_identity import compute_git_tree_identity
from .scope import ProvenanceAnchorInputs, ScopeDecision, build_provenance_anchor


DEFAULT_HARNESS_BINDING_IDENTITY = "oma7-harness:release-candidate"
DEFAULT_SCOPE_BUDGET = "mvp-first-real-g0"
DEFAULT_VERIFICATION_COMMAND = "python -m unittest discover -s tests -v"
REAL_EXECUTION_PREDICATE_KIND = "real-execution"


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
class ReleaseCandidateExecutionCapture:
    attempt_identity: AttemptIdentity
    mission_identity: MissionIdentity
    subject_identity: SubjectIdentity
    materialization_identity: MaterializationIdentity
    execution_context_identity: ExecutionContextIdentity
    verification_context_identity: VerificationContextIdentity
    scope_policy_identity: ScopePolicyIdentity
    predicate: dict[str, Any]
    execution_facts: dict[str, Any] = field(default_factory=dict)
    verification_facts: dict[str, Any] = field(default_factory=dict)
    provenance_anchor_identity: ProvenanceAnchorIdentity | None = None
    verifier_id: str | None = None


@dataclass(frozen=True)
class ReleaseCandidateReadiness:
    workspace: str
    harness_validation_ok: bool
    docker_runtime_ready: bool
    pinned_runtime_ready: bool
    auth_ready: bool
    mission_plan_ready: bool
    sandbox_preflight: str
    sandbox_execution_plan_id: str | None
    sandbox_code_home: str
    sandbox_command: tuple[str, ...]
    sandbox_workdir: str
    sandbox_network: str
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


def build_release_candidate_execution_evidence(
    capture: ReleaseCandidateExecutionCapture,
) -> Evidence:
    if capture.predicate.get("kind") != REAL_EXECUTION_PREDICATE_KIND:
        raise ValueError("release-candidate execution evidence requires real-execution predicate kind")
    required_execution_facts = {
        "run_id",
        "attempt_id",
        "evidence_root",
        "codex_binary_digest",
        "codex_version",
        "model",
        "reasoning_level",
        "harness_commit_or_digest",
        "harness_configuration_digest",
        "dataset_revision",
        "dependency_lock_digest",
        "environment_container_image_digest",
        "toolchain_identity",
    }
    missing_execution_facts = sorted(item for item in required_execution_facts if not capture.execution_facts.get(item))
    if missing_execution_facts:
        raise ValueError(f"release-candidate execution capture missing execution facts: {missing_execution_facts}")
    required_verification_facts = {
        "run_id",
        "attempt_id",
        "dataset_revision",
        "oracle_test_patch_identity",
        "harness_commit_or_digest",
        "verification_configuration_digest",
        "verifier_identity",
    }
    missing_verification_facts = sorted(item for item in required_verification_facts if not capture.verification_facts.get(item))
    if missing_verification_facts:
        raise ValueError(f"release-candidate execution capture missing verification facts: {missing_verification_facts}")
    if capture.attempt_identity.execution_context_identity is None or capture.attempt_identity.subject_identity is None:
        raise ValueError("release-candidate execution capture attempt identity is incomplete")
    if capture.attempt_identity.run_id != capture.mission_identity.identity():
        raise ValueError("release-candidate execution capture attempt does not bind to mission identity")
    if capture.attempt_identity.execution_context_identity != capture.execution_context_identity:
        raise ValueError("release-candidate execution capture attempt execution context mismatch")
    if capture.attempt_identity.subject_identity != capture.subject_identity:
        raise ValueError("release-candidate execution capture attempt subject mismatch")
    if capture.execution_facts["run_id"] != capture.attempt_identity.run_id or capture.verification_facts["run_id"] != capture.attempt_identity.run_id:
        raise ValueError("release-candidate execution capture run binding mismatch")
    if capture.execution_facts["attempt_id"] != capture.attempt_identity.attempt_id or capture.verification_facts["attempt_id"] != capture.attempt_identity.attempt_id:
        raise ValueError("release-candidate execution capture attempt binding mismatch")
    expected_execution_context = ExecutionContextIdentity(
        environment_container_image_digest=str(capture.execution_facts["environment_container_image_digest"]),
        codex_binary_digest=str(capture.execution_facts["codex_binary_digest"]),
        codex_version=str(capture.execution_facts["codex_version"]),
        model=str(capture.execution_facts["model"]),
        reasoning_level=str(capture.execution_facts["reasoning_level"]),
        harness_commit_or_digest=str(capture.execution_facts["harness_commit_or_digest"]),
        harness_configuration_digest=str(capture.execution_facts["harness_configuration_digest"]),
        dependency_lock_digest=str(capture.execution_facts["dependency_lock_digest"]),
        dataset_revision=str(capture.execution_facts["dataset_revision"]),
        toolchain_identity=str(capture.execution_facts["toolchain_identity"]),
    )
    if expected_execution_context != capture.execution_context_identity:
        raise ValueError("release-candidate execution capture execution context mismatch")
    expected_mission_identity = compute_mission_identity(
        subject_identity=capture.subject_identity,
        materialization_identity=capture.materialization_identity,
        execution_context_identity=capture.execution_context_identity,
        scope_policy_identity=capture.scope_policy_identity,
        verification_context_identity=capture.verification_context_identity,
    )
    if expected_mission_identity != capture.mission_identity:
        raise ValueError("release-candidate execution capture mission identity mismatch")
    if capture.verification_context_identity.dataset_revision != capture.verification_facts["dataset_revision"]:
        raise ValueError("release-candidate execution capture verification dataset mismatch")
    if capture.verification_context_identity.oracle_test_patch_identity != capture.verification_facts["oracle_test_patch_identity"]:
        raise ValueError("release-candidate execution capture verification oracle patch mismatch")
    if capture.verification_context_identity.harness_commit_or_digest != capture.verification_facts["harness_commit_or_digest"]:
        raise ValueError("release-candidate execution capture verification harness mismatch")
    if capture.verification_context_identity.verification_configuration_digest != capture.verification_facts["verification_configuration_digest"]:
        raise ValueError("release-candidate execution capture verification digest mismatch")
    if capture.verification_context_identity.verifier_identity != capture.verification_facts["verifier_identity"]:
        raise ValueError("release-candidate execution capture verification context mismatch")
    if (
        capture.verification_context_identity.verifier_environment_image_digest is not None
        and capture.verification_context_identity.verifier_environment_image_digest
        != capture.execution_context_identity.environment_container_image_digest
    ):
        raise ValueError("release-candidate execution capture verification environment mismatch")
    if capture.verifier_id is not None and capture.verifier_id != capture.verification_context_identity.verifier_identity:
        raise ValueError("release-candidate execution capture verifier binding mismatch")
    if capture.provenance_anchor_identity is None:
        provenance = build_provenance_anchor(
            ProvenanceAnchorInputs(
                subject_identity=capture.subject_identity,
                execution_context_identity=capture.execution_context_identity,
                verification_context_identity=capture.verification_context_identity,
                scope_policy_identity=capture.scope_policy_identity,
                run_id=capture.attempt_identity.run_id,
                verifier_id=capture.verifier_id or capture.verification_context_identity.verifier_identity or "oma7-first-real-g0-verifier",
                cost_ledger_head=None,
                cost_ledger_event_count=None,
                scope_decision=ScopeDecision.ALLOW,
                scope_change_id=f"release-candidate:{_digest(json.dumps(capture.predicate, sort_keys=True, separators=(',', ':'), ensure_ascii=False))}",
            )
        ).identity
    else:
        provenance = capture.provenance_anchor_identity
    return Evidence(
        subject_identity=capture.subject_identity,
        materialization_identity=capture.materialization_identity,
        execution_context_identity=capture.execution_context_identity,
        verification_context_identity=capture.verification_context_identity,
        scope_policy_identity=capture.scope_policy_identity,
        provenance_anchor_identity=provenance,
        result=ResultStatus.PASS,
        verifier_id=capture.verification_context_identity.verifier_identity,
        run_id=capture.attempt_identity.run_id,
        predicate=capture.predicate,
    )


def persist_release_candidate_execution_artifacts(
    *,
    capture: ReleaseCandidateExecutionCapture,
    accounting_cost_units: int = 1,
    accounting_reason: str = "real-execution",
) -> PersistedExecutionArtifacts:
    if capture.predicate.get("kind") != REAL_EXECUTION_PREDICATE_KIND:
        raise ValueError("release-candidate execution artifacts require real-execution predicate kind")
    evidence = build_release_candidate_execution_evidence(capture)
    return persist_canonical_execution_artifacts(
        run_id=capture.attempt_identity.run_id,
        evidence=evidence,
        base_dir=Path(capture.execution_facts["evidence_root"]),
        accounting_cost_units=accounting_cost_units,
        accounting_reason=accounting_reason,
    )


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
    sandbox_result = run_sandbox_preflight(
        SandboxPreflightConfig(
            workspace=workspace,
            pins=pins,
            approval_noninteractive=True,
            automatic_escalation_disabled=True,
            codex_home=Path(os.environ.get("CODEX_HOME") or os.environ.get("OMA7_EPHEMERAL_CODEX_HOME") or Path(tempfile.gettempdir()) / "oma7-ephemeral-codex-home"),
            command=DEFAULT_SANDBOX_COMMAND,
            workdir="/workspace",
            network="none",
            mounts=((workspace, "/workspace", "rw"),),
            environment=(),
        )
    )
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
        sandbox_preflight=sandbox_result.result.value,
        sandbox_execution_plan_id=sandbox_result.execution_plan_identity,
        sandbox_code_home=sandbox_result.codex_home,
        sandbox_command=sandbox_result.command,
        sandbox_workdir=sandbox_result.workdir,
        sandbox_network=sandbox_result.network,
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
