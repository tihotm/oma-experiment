from __future__ import annotations

import subprocess
import tempfile
import unittest
import uuid
import json
import os
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.control_plane import (
    ControlPolicyIdentity,
    FailureClassification,
    RetryBudget,
    SupervisorControlRecord,
    SupervisorState,
    validate_control_record,
    can_start_attempt,
    classify_failure,
    classify_restart,
    create_control_record as _create_control_record,
    duplicate_acceptance_prevented,
    duplicate_execution_prevented,
    load_control_record,
    new_attempt_identity,
    record_attempt,
    write_control_record,
    update_budget_state,
)
from oma7.docker_lifecycle import (
    DockerCapability,
    DockerContainerSpec,
    build_synthetic_acceptance_observation,
    docker_create,
    docker_executable,
    docker_exec,
    docker_inspect_container,
    docker_list_containers,
    docker_remove,
    docker_start,
    docker_stop,
    docker_context,
    docker_version,
    docker_capability,
    docker_runtime_status,
    freeze_workspace_after_quiescence,
    materialize_verifier_copy,
    run_synthetic_verifier_stage,
    temp_probe_dirs,
)
from oma7.preflight import DEFAULT_CODEX_IMAGE_REF
from oma7.lifecycle import AcceptanceOutcome, LifecycleState, evaluate_acceptance
from oma7.models import (
    Evidence,
    MaterializationIdentity,
    ProvenanceAnchorIdentity,
    ResultStatus,
    ScopePolicyIdentity,
    SubjectIdentity,
    VerificationContextIdentity,
)
from oma7.scope import ProvenanceAnchorInputs, ScopeDecision, ScopePolicy, build_provenance_anchor, evaluate_scope_change, ScopeChange, ScopeOperation, ScopeObjectType
from oma7.snapshot import freeze_snapshot


PINNED_IMAGE = DEFAULT_CODEX_IMAGE_REF



def create_control_record(mission_id: str, run_id: str, budget) -> "oma7.control_plane.SupervisorControlRecord":
    from oma7.models import SubjectIdentity, MaterializationIdentity, ExecutionContextIdentity, ScopePolicyIdentity, compute_mission_identity
    from oma7.control_plane import control_policy_identity_from_policy
    subject = SubjectIdentity(git_tree="tree", git_commit="commit", path=".")
    materialization = MaterializationIdentity(subject_identity=subject, canonical_root_descriptor="git:root")
    execution = ExecutionContextIdentity(environment_container_image_digest="env", codex_binary_digest="codex", codex_version="0.1.0", model="o-model", reasoning_level="high", harness_commit_or_digest="harness", harness_configuration_digest="cfg", dependency_lock_digest="lock", dataset_revision="data", toolchain_identity="tool")
    scope = ScopePolicyIdentity(allowed_scope_path_policy=("**",), protected_semantic_roles=(), explicit_sensitive_change_authorizations=(), scope_budget="b", task_specific_exceptions=(), rule_schema_version="v1")
    mission = compute_mission_identity(subject_identity=subject, materialization_identity=materialization, execution_context_identity=execution, scope_policy_identity=scope)
    policy = control_policy_identity_from_policy(max_attempts=budget.max_attempts, max_elapsed_time_seconds=budget.max_elapsed_time_seconds, max_execution_time_per_attempt_seconds=budget.max_execution_time_per_attempt_seconds, retryable_classifications=(), non_retryable_classifications=(), escalation_reasons=())
    return _create_control_record(
        run_id=run_id,
        budget=budget,
        mission_identity=mission,
        control_policy_identity=policy,
        harness_binding_identity="harness-1:cfg-1",
        subject_identity=subject,
        execution_context_identity=execution,
        scope_policy_identity=scope,
    )


def _docker_available() -> bool:
    try:
        docker = docker_executable()
        capability, _ = docker_capability(docker)
        return capability == DockerCapability.READY
    except Exception:
        return False


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(["git", *cmd], cwd=cwd, check=True, capture_output=True, text=True)


def _subject() -> SubjectIdentity:
    return SubjectIdentity(git_tree="tree", git_commit="commit", path=".")


def _materialization(subject: SubjectIdentity) -> MaterializationIdentity:
    return MaterializationIdentity(subject_identity=subject, canonical_root_descriptor="git:root")


def _execution() -> VerificationContextIdentity:
    raise AssertionError


def _verification(verifier_id: str = "verifier-1") -> VerificationContextIdentity:
    return VerificationContextIdentity(
        dataset_revision="dataset-1",
        oracle_test_patch_identity="oracle-1",
        fail_to_pass=(),
        pass_to_pass=(),
        harness_commit_or_digest="harness-1",
        verification_configuration_digest="verify-cfg-1",
        verifier_environment_image_digest="img",
        verifier_identity=verifier_id,
    )


def _scope_identity() -> ScopePolicyIdentity:
    return ScopePolicyIdentity(
        allowed_scope_path_policy=("src/**",),
        protected_semantic_roles=("oracle",),
        explicit_sensitive_change_authorizations=(),
        scope_budget="budget",
        task_specific_exceptions=(),
        rule_schema_version="scope/v1",
    )


class SupervisionDockerTests(unittest.TestCase):
    def _provenance(self, subject: SubjectIdentity, verification: VerificationContextIdentity, scope_identity: ScopePolicyIdentity, run_id: str, verifier_id: str) -> ProvenanceAnchorIdentity:
        return build_provenance_anchor(
            ProvenanceAnchorInputs(
                subject_identity=subject,
                execution_context_identity=__import__("oma7.models", fromlist=["ExecutionContextIdentity"]).ExecutionContextIdentity(
                    environment_container_image_digest="img",
                    codex_binary_digest="bin",
                    codex_version="0",
                    model="synthetic",
                    reasoning_level="high",
                    harness_commit_or_digest="h",
                    harness_configuration_digest="c",
                    dependency_lock_digest="d",
                    dataset_revision="dataset-1",
                    toolchain_identity="toolchain-1",
                ),
                verification_context_identity=verification,
                scope_policy_identity=scope_identity,
                run_id=run_id,
                verifier_id=verifier_id,
                cost_ledger_head="ledger-1",
                cost_ledger_event_count=1,
                scope_decision=ScopeDecision.ALLOW,
                scope_change_id="change-1",
            )
        ).identity

    def _scope_eval(self, subject: SubjectIdentity, materialization: MaterializationIdentity):
        policy = ScopePolicy(("allowed/**", "tests/**"))
        change = ScopeChange(
            operation=ScopeOperation.MODIFY,
            before_path="allowed/file.txt",
            after_path="allowed/file.txt",
            before_object_type=ScopeObjectType.FILE,
            after_object_type=ScopeObjectType.FILE,
            before_identity="before",
            after_identity="after",
        )
        return evaluate_scope_change(change, policy, subject_identity=subject, materialization_identity=materialization)

    def test_restart_resume_and_verification_reuse(self) -> None:
        if not _docker_available():
            self.skipTest("docker CLI unavailable")
        docker = docker_executable()
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        workspace, readonly, oracle, _ = temp_probe_dirs()
        _git(["init"], workspace)
        _git(["config", "user.email", "test@example.com"], workspace)
        _git(["config", "user.name", "Test User"], workspace)
        (workspace / "result.txt").write_text("OMA7_SYNTHETIC_EXECUTOR_OK", encoding="utf-8")
        _git(["add", "result.txt"], workspace)
        _git(["commit", "-m", "init"], workspace)
        frozen_identity, frozen_dir = freeze_snapshot(workspace)
        control = create_control_record(mission_id="mission-1", run_id=run_id, budget=RetryBudget(2, 30, 10))
        executor_name = f"oma7-executor-{uuid.uuid4().hex[:8]}"
        executor_spec = DockerContainerSpec(
            image_ref=PINNED_IMAGE,
            name=executor_name,
            workspace_host_path=workspace,
            readonly_host_path=readonly,
            network="none",
            labels=(("oma7.run_id", run_id), ("oma7.attempt_id", f"{run_id}:1"), ("oma7.role", "executor")),
            command=("sh", "-lc", "sleep 3600"),
        )
        executor_id = docker_create(docker, executor_spec, run_id=run_id)
        docker_start(docker, executor_id)
        control = control.with_attempt(record_attempt(new_attempt_identity(run_id, 1, subject_identity=_subject()), SupervisorState.RUNNING))
        write_control_record(workspace / "control.json", control)
        observation = classify_restart(load_control_record(workspace / "control.json"), runtime_executor_active=True)
        self.assertEqual(observation, SupervisorState.RUNNING)
        try:
            docker_stop(docker, executor_id)
            freeze_workspace_after_quiescence(docker, executor_id, workspace)
            control = control.__class__(**{**control.__dict__, "state": SupervisorState.VERIFYING, "current_attempt_id": f"{run_id}:1"})
            write_control_record(workspace / "control.json", control)
            loaded = load_control_record(workspace / "control.json")
            self.assertEqual(classify_restart(loaded, frozen_submission_exists=True, verifier_complete=False), SupervisorState.VERIFYING)
            verifier = run_synthetic_verifier_stage(
                docker=docker,
                image_ref=PINNED_IMAGE,
                executor_container_id=executor_id,
                frozen_workspace=frozen_dir,
                oracle_workspace=oracle,
                verifier_identity="verifier-1",
                verifier_configuration_digest="verify-cfg-1",
                harness_commit_or_digest="harness-1",
                dataset_revision="dataset-1",
                oracle_test_patch_identity="oracle-1",
            )
            self.assertTrue(verifier.functional_pass)
            subject = _subject()
            materialization = _materialization(subject)
            scope_identity = _scope_identity()
            provenance = self._provenance(subject, _verification(), scope_identity, run_id, "verifier-1")
            evidence = Evidence(
                subject_identity=subject,
                materialization_identity=materialization,
                execution_context_identity=__import__("oma7.models", fromlist=["ExecutionContextIdentity"]).ExecutionContextIdentity(
                    environment_container_image_digest="img",
                    codex_binary_digest="bin",
                    codex_version="0",
                    model="synthetic",
                    reasoning_level="high",
                    harness_commit_or_digest="h",
                    harness_configuration_digest="c",
                    dependency_lock_digest="d",
                    dataset_revision="dataset-1",
                    toolchain_identity="toolchain-1",
                ),
                verification_context_identity=verifier.verification_context_identity,
                scope_policy_identity=scope_identity,
                provenance_anchor_identity=provenance,
                result=ResultStatus.PASS,
                verifier_id="verifier-1",
                run_id=run_id,
            )
            scope_eval = self._scope_eval(subject, materialization)
            decision = evaluate_acceptance(build_synthetic_acceptance_observation(
                evidence=evidence,
                subject_identity=subject,
                materialization_identity=materialization,
                execution_context_identity=evidence.execution_context_identity,
                verification_context_identity=verifier.verification_context_identity,
                scope_policy_identity=scope_identity,
                provenance_anchor_identity=provenance,
                scope_evaluation=scope_eval,
            ))
            self.assertEqual(decision.outcome, AcceptanceOutcome.EVAL_DONE)
        finally:
            docker_remove(docker, executor_id, force=True)
        self.assertEqual(docker_list_containers(docker, run_id=run_id), [])

    def test_active_container_recovery_and_foreign_container_untouched(self) -> None:
        if not _docker_available():
            self.skipTest("docker CLI unavailable")
        docker = docker_executable()
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        foreign_run_id = f"foreign-{uuid.uuid4().hex[:8]}"
        workspace, readonly, _, _ = temp_probe_dirs()
        _git(["init"], workspace)
        _git(["config", "user.email", "test@example.com"], workspace)
        _git(["config", "user.name", "Test User"], workspace)
        (workspace / "result.txt").write_text("OMA7_SYNTHETIC_EXECUTOR_OK", encoding="utf-8")
        _git(["add", "result.txt"], workspace)
        _git(["commit", "-m", "init"], workspace)
        control = create_control_record(mission_id="mission-1", run_id=run_id, budget=RetryBudget(2, 30, 10))
        executor_spec = DockerContainerSpec(
            image_ref=PINNED_IMAGE,
            name=f"oma7-executor-{uuid.uuid4().hex[:8]}",
            workspace_host_path=workspace,
            readonly_host_path=readonly,
            network="none",
            labels=(("oma7.run_id", run_id), ("oma7.attempt_id", f"{run_id}:1"), ("oma7.role", "executor")),
            command=("sh", "-lc", "sleep 3600"),
        )
        foreign_spec = DockerContainerSpec(
            image_ref=PINNED_IMAGE,
            name=f"oma7-foreign-{uuid.uuid4().hex[:8]}",
            workspace_host_path=workspace,
            readonly_host_path=None,
            network="none",
            labels=(("oma7.run_id", foreign_run_id), ("oma7.role", "foreign")),
            command=("sh", "-lc", "sleep 3600"),
        )
        executor_id = docker_create(docker, executor_spec, run_id=run_id)
        foreign_id = docker_create(docker, foreign_spec, run_id=foreign_run_id)
        docker_start(docker, executor_id)
        docker_start(docker, foreign_id)
        try:
            control = control.with_attempt(record_attempt(new_attempt_identity(run_id, 1, subject_identity=_subject()), SupervisorState.RUNNING))
            control = control.__class__(**{**control.__dict__, "state": SupervisorState.RUNNING, "current_attempt_id": f"{run_id}:1"})
            write_control_record(workspace / "control.json", control)
            self.assertEqual(classify_restart(load_control_record(workspace / "control.json"), runtime_executor_active=True), SupervisorState.RUNNING)
            foreign_before = docker_inspect_container(docker, foreign_id)
            self.assertEqual(foreign_before.label_run_id, foreign_run_id)
            docker_stop(docker, executor_id)
            self.assertEqual(classify_restart(load_control_record(workspace / "control.json"), frozen_submission_exists=False, verifier_complete=False), SupervisorState.RETRYABLE_FAILURE)
            foreign_after = docker_inspect_container(docker, foreign_id)
            self.assertEqual(foreign_after.label_run_id, foreign_run_id)
            self.assertTrue(docker_inspect_container(docker, executor_id).label_run_id == run_id)
        finally:
            docker_remove(docker, executor_id, force=True)
            docker_remove(docker, foreign_id, force=True)
        self.assertEqual(docker_list_containers(docker, run_id=run_id), [])
        self.assertEqual(docker_list_containers(docker, run_id=foreign_run_id), [])

    def test_corrupt_control_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            path.write_text("{", encoding="utf-8")
            self.assertIsNone(load_control_record(path))
            self.assertEqual(classify_restart(None), SupervisorState.ESCALATION_REQUIRED)

    def test_missing_running_container_not_treated_as_success_and_policy_rejects(self) -> None:
        if not _docker_available():
            self.skipTest("docker CLI unavailable")
        record = create_control_record(mission_id="mission-1", run_id="run-missing", budget=RetryBudget(2, 30, 10))
        attempt = record_attempt(new_attempt_identity("run-missing", 1, subject_identity=_subject()), SupervisorState.RUNNING)
        record = record.with_attempt(attempt)
        record = record.__class__(**{**record.__dict__, "state": SupervisorState.RUNNING})
        self.assertTrue(validate_control_record(record))
        self.assertEqual(classify_restart(record, runtime_executor_active=False), SupervisorState.RETRYABLE_FAILURE)
        self.assertNotEqual(classify_restart(record, runtime_executor_active=False), SupervisorState.ACCEPTED)

    def test_conflicting_runtime_facts_fail_closed(self) -> None:
        if not _docker_available():
            self.skipTest("docker CLI unavailable")
        record = create_control_record(mission_id="mission-1", run_id="run-a", budget=RetryBudget(2, 30, 10))
        record = record.__class__(**{**record.__dict__, "state": SupervisorState.VERIFYING, "current_attempt_id": "run-a:1"})
        bad_budget = record.__class__(**{**record.__dict__, "budget": RetryBudget(-1, 30, 10)})
        self.assertFalse(validate_control_record(bad_budget))
        self.assertEqual(classify_restart(bad_budget, frozen_submission_exists=True, verifier_complete=True), SupervisorState.ESCALATION_REQUIRED)

    def test_active_container_recovery_and_foreign_container_untouched_runtime(self) -> None:
        if not _docker_available():
            self.skipTest("docker CLI unavailable")
        docker = docker_executable()
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        foreign_run_id = f"foreign-{uuid.uuid4().hex[:8]}"
        workspace, readonly, _, _ = temp_probe_dirs()
        _git(["init"], workspace)
        _git(["config", "user.email", "test@example.com"], workspace)
        _git(["config", "user.name", "Test User"], workspace)
        (workspace / "result.txt").write_text("OMA7_SYNTHETIC_EXECUTOR_OK", encoding="utf-8")
        _git(["add", "result.txt"], workspace)
        _git(["commit", "-m", "init"], workspace)
        executor_spec = DockerContainerSpec(
            image_ref=PINNED_IMAGE,
            name=f"oma7-executor-{uuid.uuid4().hex[:8]}",
            workspace_host_path=workspace,
            readonly_host_path=readonly,
            network="none",
            labels=(("oma7.run_id", run_id), ("oma7.attempt_id", f"{run_id}:1"), ("oma7.role", "executor")),
            command=("sh", "-lc", "sleep 3600"),
        )
        foreign_spec = DockerContainerSpec(
            image_ref=PINNED_IMAGE,
            name=f"oma7-foreign-{uuid.uuid4().hex[:8]}",
            workspace_host_path=workspace,
            readonly_host_path=None,
            network="none",
            labels=(("oma7.run_id", foreign_run_id), ("oma7.role", "foreign")),
            command=("sh", "-lc", "sleep 3600"),
        )
        executor_id = docker_create(docker, executor_spec, run_id=run_id)
        foreign_id = docker_create(docker, foreign_spec, run_id=foreign_run_id)
        docker_start(docker, executor_id)
        docker_start(docker, foreign_id)
        try:
            foreign_before = docker_inspect_container(docker, foreign_id)
            self.assertEqual(foreign_before.label_run_id, foreign_run_id)
            record = create_control_record(mission_id="mission-1", run_id=run_id, budget=RetryBudget(2, 30, 10))
            record = record.with_attempt(record_attempt(new_attempt_identity(run_id, 1, subject_identity=_subject()), SupervisorState.RUNNING))
            record = record.__class__(**{**record.__dict__, "state": SupervisorState.RUNNING})
            self.assertEqual(classify_restart(record, runtime_executor_active=True), SupervisorState.RUNNING)
            self.assertTrue(docker_inspect_container(docker, executor_id).running)
            foreign_after = docker_inspect_container(docker, foreign_id)
            self.assertEqual(foreign_after.label_run_id, foreign_run_id)
        finally:
            docker_stop(docker, executor_id)
            docker_stop(docker, foreign_id)
            docker_remove(docker, executor_id, force=True)
            docker_remove(docker, foreign_id, force=True)

    def test_cross_run_docker_isolation_runtime(self) -> None:
        if not _docker_available():
            self.skipTest("docker CLI unavailable")
        docker = docker_executable()
        workspace, readonly, _, _ = temp_probe_dirs()
        _git(["init"], workspace)
        _git(["config", "user.email", "test@example.com"], workspace)
        _git(["config", "user.name", "Test User"], workspace)
        (workspace / "result.txt").write_text("OMA7_SYNTHETIC_EXECUTOR_OK", encoding="utf-8")
        _git(["add", "result.txt"], workspace)
        _git(["commit", "-m", "init"], workspace)
        run_a = f"run-{uuid.uuid4().hex[:8]}"
        run_b = f"run-{uuid.uuid4().hex[:8]}"
        spec_a = DockerContainerSpec(
            image_ref=PINNED_IMAGE,
            name=f"oma7-cross-a-{uuid.uuid4().hex[:8]}",
            workspace_host_path=workspace,
            readonly_host_path=readonly,
            network="none",
            labels=(("oma7.run_id", run_a), ("oma7.role", "executor")),
            command=("sh", "-lc", "sleep 3600"),
        )
        spec_b = DockerContainerSpec(
            image_ref=PINNED_IMAGE,
            name=f"oma7-cross-b-{uuid.uuid4().hex[:8]}",
            workspace_host_path=workspace,
            readonly_host_path=readonly,
            network="none",
            labels=(("oma7.run_id", run_b), ("oma7.role", "executor")),
            command=("sh", "-lc", "sleep 3600"),
        )
        a_id = docker_create(docker, spec_a, run_id=run_a)
        b_id = docker_create(docker, spec_b, run_id=run_b)
        docker_start(docker, a_id)
        docker_start(docker, b_id)
        try:
            self.assertEqual([item.label_run_id for item in docker_list_containers(docker, run_id=run_a)], [run_a])
            self.assertEqual([item.label_run_id for item in docker_list_containers(docker, run_id=run_b)], [run_b])
            docker_stop(docker, a_id)
            docker_remove(docker, a_id, force=True)
            self.assertEqual(docker_list_containers(docker, run_id=run_a), [])
            self.assertEqual([item.label_run_id for item in docker_list_containers(docker, run_id=run_b)], [run_b])
        finally:
            docker_stop(docker, b_id)
            docker_remove(docker, b_id, force=True)

    def test_oracle_isolation_across_retries_runtime(self) -> None:
        if not _docker_available():
            self.skipTest("docker CLI unavailable")
        docker = docker_executable()
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        workspace, readonly, oracle_a, _ = temp_probe_dirs()
        _git(["init"], workspace)
        _git(["config", "user.email", "test@example.com"], workspace)
        _git(["config", "user.name", "Test User"], workspace)
        (workspace / "result.txt").write_text("OMA7_SYNTHETIC_EXECUTOR_OK", encoding="utf-8")
        _git(["add", "result.txt"], workspace)
        _git(["commit", "-m", "init"], workspace)
        frozen_workspace = freeze_snapshot(workspace)[1]
        first_id = docker_create(
            docker,
            DockerContainerSpec(
                image_ref=PINNED_IMAGE,
                name=f"oma7-oracle-a-{uuid.uuid4().hex[:8]}",
                workspace_host_path=workspace,
                readonly_host_path=readonly,
                network="none",
                labels=(("oma7.run_id", run_id), ("oma7.role", "executor")),
                command=("sh", "-lc", "sleep 3600"),
            ),
            run_id=run_id,
        )
        docker_start(docker, first_id)
        docker_stop(docker, first_id)
        first = run_synthetic_verifier_stage(
            docker=docker,
            image_ref=PINNED_IMAGE,
            executor_container_id=first_id,
            frozen_workspace=frozen_workspace,
            oracle_workspace=oracle_a,
            verifier_identity="verifier-a",
            verifier_configuration_digest="verify-cfg-a",
            harness_commit_or_digest="harness-a",
            dataset_revision="dataset-a",
            oracle_test_patch_identity="oracle-a",
        )
        oracle_b = temp_probe_dirs()[2]
        second_id = docker_create(
            docker,
            DockerContainerSpec(
                image_ref=PINNED_IMAGE,
                name=f"oma7-oracle-b-{uuid.uuid4().hex[:8]}",
                workspace_host_path=workspace,
                readonly_host_path=readonly,
                network="none",
                labels=(("oma7.run_id", run_id), ("oma7.role", "executor")),
                command=("sh", "-lc", "sleep 3600"),
            ),
            run_id=run_id,
        )
        docker_start(docker, second_id)
        docker_stop(docker, second_id)
        second = run_synthetic_verifier_stage(
            docker=docker,
            image_ref=PINNED_IMAGE,
            executor_container_id=second_id,
            frozen_workspace=frozen_workspace,
            oracle_workspace=oracle_b,
            verifier_identity="verifier-b",
            verifier_configuration_digest="verify-cfg-b",
            harness_commit_or_digest="harness-b",
            dataset_revision="dataset-b",
            oracle_test_patch_identity="oracle-b",
        )
        try:
            self.assertTrue(first.functional_pass)
            self.assertTrue(second.functional_pass)
            self.assertNotEqual(first.oracle_workspace, second.oracle_workspace)
            self.assertEqual((first.oracle_workspace / "oracle.txt").read_text(encoding="utf-8"), "OMA7_SYNTHETIC_EXECUTOR_OK")
            self.assertEqual((second.oracle_workspace / "oracle.txt").read_text(encoding="utf-8"), "OMA7_SYNTHETIC_EXECUTOR_OK")
        finally:
            docker_remove(docker, first_id, force=True)
            docker_remove(docker, second_id, force=True)



if __name__ == "__main__":
    unittest.main()
