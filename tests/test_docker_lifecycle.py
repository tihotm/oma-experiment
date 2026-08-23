from __future__ import annotations

import tempfile
import unittest
import subprocess
import os
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.docker_lifecycle import (
    DockerContainerSpec,
    SyntheticLifecycleResult,
    build_execution_context_identity,
    build_verification_context_identity,
    build_synthetic_acceptance_observation,
    docker_cleanup_run,
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
    docker_runtime_status,
    ensure_container_quiescent,
    freeze_workspace_after_quiescence,
    materialize_verifier_copy,
    run_synthetic_lifecycle,
    run_synthetic_verifier_stage,
    temp_probe_dirs,
)
from oma7.preflight import DEFAULT_CODEX_IMAGE_REF
from oma7.models import Evidence, ResultStatus, SubjectIdentity, VerificationContextIdentity
from oma7.scope import ProvenanceAnchorInputs, ScopeDecision, ScopePolicy, ScopeChange, ScopeOperation, ScopeObjectType, evaluate_scope_change, build_provenance_anchor
from oma7.lifecycle import evaluate_acceptance
from oma7.snapshot import freeze_snapshot
from oma7.verifier import verify_snapshot_is_copy


PINNED_IMAGE = DEFAULT_CODEX_IMAGE_REF


def _docker_available() -> bool:
    try:
        docker = docker_executable()
        available, _ = docker_runtime_status(docker)
        return available and docker_context(docker) is not None
    except Exception:
        return False


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(["git", *cmd], cwd=cwd, check=True, capture_output=True, text=True)


class DockerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not _docker_available():
            raise unittest.SkipTest("docker CLI unavailable")

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def materialization(self, subject: SubjectIdentity | None = None):
        subject = subject or self.subject()
        return __import__("oma7.models", fromlist=["MaterializationIdentity"]).MaterializationIdentity(
            subject_identity=subject,
            canonical_root_descriptor="git:root",
            symlink_topology=(("a", "b"),),
            hardlink_topology=(("c", "d"),),
            worktree_reference_identity="worktree-1",
            mounted_reference_artifact_identities=("ref-1",),
            cache_manifest_digest="cache-1",
        )

    def execution(self, digest: str = "env-digest"):
        return __import__("oma7.models", fromlist=["ExecutionContextIdentity"]).ExecutionContextIdentity(
            environment_container_image_digest=digest,
            codex_binary_digest="codex-bin",
            codex_version="0.1.0",
            model="o-model",
            reasoning_level="high",
            harness_commit_or_digest="harness-1",
            harness_configuration_digest="cfg-1",
            dependency_lock_digest="lock-1",
            dataset_revision="dataset-1",
            toolchain_identity="toolchain-1",
        )

    def verification(self, revision: str = "dataset-1", oracle: str = "oracle-1"):
        return VerificationContextIdentity(
            dataset_revision=revision,
            oracle_test_patch_identity=oracle,
            fail_to_pass=("f1", "f2"),
            pass_to_pass=("p1",),
            harness_commit_or_digest="harness-1",
            verification_configuration_digest="verify-cfg-1",
            verifier_environment_image_digest="verifier-img-1",
            verifier_identity="verifier-1",
        )

    def scope_policy(self, scope_budget: str = "budget-1", exceptions: tuple[str, ...] = ("exc-1",)):
        return __import__("oma7.models", fromlist=["ScopePolicyIdentity"]).ScopePolicyIdentity(
            allowed_scope_path_policy=("src/**", "tests/**"),
            protected_semantic_roles=("oracle", "provenance"),
            explicit_sensitive_change_authorizations=("manifest",),
            scope_budget=scope_budget,
            task_specific_exceptions=exceptions,
            rule_schema_version="scope/v1",
        )

    def scope_runtime_policy(self, allowed: tuple[str, ...] = ("allowed/**", "generated/**", "tests/**")):
        return ScopePolicy(allowed_scope_path_policy=allowed)

    def scope_change(self, **overrides):
        base = dict(
            operation=ScopeOperation.MODIFY,
            before_path="allowed/file.txt",
            after_path="allowed/file.txt",
            before_object_type=ScopeObjectType.FILE,
            after_object_type=ScopeObjectType.FILE,
            before_identity="before-1",
            after_identity="after-1",
            mutation_kind=__import__("oma7.scope", fromlist=["ScopeMutationKind"]).ScopeMutationKind.PRIMARY,
            parent_change_id=None,
            explicitly_allowed=False,
            change_id="change-1",
        )
        base.update(overrides)
        return ScopeChange(**base)

    def subject(self) -> SubjectIdentity:
        return SubjectIdentity(git_tree="tree", git_commit="commit", path=".")

    def test_identity_builders_are_stable_and_sensitive(self) -> None:
        exec_a = build_execution_context_identity(
            image_digest="sha256:image-a",
            codex_binary_digest="sha256:codex-a",
            codex_version="0",
            model="synthetic",
            reasoning_level="high",
            harness_commit_or_digest="harness-a",
            harness_configuration_digest="cfg-a",
            dependency_lock_digest="lock-a",
            dataset_revision="dataset-a",
            toolchain_identity="toolchain-a",
        )
        exec_b = build_execution_context_identity(
            image_digest="sha256:image-a",
            codex_binary_digest="sha256:codex-a",
            codex_version="0",
            model="synthetic",
            reasoning_level="high",
            harness_commit_or_digest="harness-a",
            harness_configuration_digest="cfg-a",
            dependency_lock_digest="lock-a",
            dataset_revision="dataset-a",
            toolchain_identity="toolchain-a",
        )
        exec_c = build_execution_context_identity(
            image_digest="sha256:image-b",
            codex_binary_digest="sha256:codex-a",
            codex_version="0",
            model="synthetic",
            reasoning_level="high",
            harness_commit_or_digest="harness-a",
            harness_configuration_digest="cfg-a",
            dependency_lock_digest="lock-a",
            dataset_revision="dataset-a",
            toolchain_identity="toolchain-a",
        )
        self.assertEqual(exec_a.identity(), exec_b.identity())
        self.assertNotEqual(exec_a.identity(), exec_c.identity())

        ver_a = build_verification_context_identity(
            dataset_revision="dataset-a",
            oracle_test_patch_identity="oracle-a",
            fail_to_pass=("f1",),
            pass_to_pass=("p1",),
            harness_commit_or_digest="harness-a",
            verification_configuration_digest="verify-a",
            verifier_environment_image_digest="sha256:verifier-a",
            verifier_identity="verifier-a",
        )
        ver_b = build_verification_context_identity(
            dataset_revision="dataset-a",
            oracle_test_patch_identity="oracle-a",
            fail_to_pass=("f1",),
            pass_to_pass=("p1",),
            harness_commit_or_digest="harness-a",
            verification_configuration_digest="verify-a",
            verifier_environment_image_digest="sha256:verifier-a",
            verifier_identity="verifier-a",
        )
        ver_c = build_verification_context_identity(
            dataset_revision="dataset-a",
            oracle_test_patch_identity="oracle-b",
            fail_to_pass=("f1",),
            pass_to_pass=("p1",),
            harness_commit_or_digest="harness-a",
            verification_configuration_digest="verify-a",
            verifier_environment_image_digest="sha256:verifier-a",
            verifier_identity="verifier-a",
        )
        self.assertEqual(ver_a.identity(), ver_b.identity())
        self.assertNotEqual(ver_a.identity(), ver_c.identity())

    def test_subject_identity_path_independence(self) -> None:
        subject_a = SubjectIdentity(git_tree="tree-a", git_commit="commit-a", path="A")
        subject_b = SubjectIdentity(git_tree="tree-a", git_commit="commit-a", path="B")
        subject_c = SubjectIdentity(git_tree="tree-b", git_commit="commit-a", path="A")
        self.assertEqual(subject_a.identity(), subject_b.identity())
        self.assertNotEqual(subject_a.identity(), subject_c.identity())

    def test_synthetic_lifecycle_probe_executes_and_cleans_up(self) -> None:
        workspace, readonly, oracle, outside = temp_probe_dirs()
        result = run_synthetic_lifecycle(
            docker=docker_executable(),
            image_ref=PINNED_IMAGE,
            workspace=workspace,
            readonly_workspace=readonly,
            oracle_workspace=oracle,
            host_outside_workspace=outside,
        )
        self.assertTrue(result.workspace_write_proven)
        self.assertTrue(result.readonly_read_succeeded)
        self.assertTrue(result.readonly_write_attempted)
        self.assertFalse(result.readonly_write_succeeded)
        self.assertTrue(result.cleanup_proven)

    def test_verifier_copy_is_independent(self) -> None:
        workspace, readonly, oracle, _ = temp_probe_dirs()
        _git(["init"], workspace)
        _git(["config", "user.email", "test@example.com"], workspace)
        _git(["config", "user.name", "Test User"], workspace)
        (workspace / "result.txt").write_text("OMA7_SYNTHETIC_EXECUTOR_OK", encoding="utf-8")
        _git(["add", "result.txt"], workspace)
        _git(["commit", "-m", "init"], workspace)
        frozen_identity, frozen_dir = freeze_snapshot(workspace)
        verifier_copy = materialize_verifier_copy(frozen_dir)
        self.assertNotEqual(verifier_copy.resolve(), frozen_dir.resolve())
        (workspace / "result.txt").write_text("changed", encoding="utf-8")
        self.assertEqual((verifier_copy / "result.txt").read_text(encoding="utf-8"), "OMA7_SYNTHETIC_EXECUTOR_OK")
        (verifier_copy / "result.txt").write_text("copy-changed", encoding="utf-8")
        self.assertEqual((frozen_dir / "result.txt").read_text(encoding="utf-8"), "OMA7_SYNTHETIC_EXECUTOR_OK")
        self.assertTrue(frozen_identity.identity())

    def test_real_docker_container_lifecycle_and_cleanup_by_label(self) -> None:
        docker = docker_executable()
        workspace, readonly, _, _ = temp_probe_dirs()
        (readonly / "README.txt").write_text("readonly\n", encoding="utf-8")
        spec = DockerContainerSpec(
            image_ref=PINNED_IMAGE,
            name="oma7-test-container",
            workspace_host_path=workspace,
            readonly_host_path=readonly,
            network="none",
            labels=(("oma7.extra", "true"),),
            command=("sh", "-lc", "sleep 3600"),
        )
        container_id = docker_create(docker, spec, run_id="run-test")
        try:
            start = docker_start(docker, container_id)
            self.assertTrue(start.succeeded)
            obs = docker_inspect_container(docker, container_id)
            self.assertTrue(obs.running)
            isolation = docker_exec(
                docker,
                container_id,
                ["sh", "-lc", "test ! -e /oracle-sentinel/oracle-sentinel.txt && test ! -e /host-outside/outside.txt"],
            )
            self.assertTrue(isolation.succeeded)
            network_probe = docker_exec(
                docker,
                container_id,
                [
                    "sh",
                    "-lc",
                    "if command -v python3 >/dev/null 2>&1; then python3 -c 'import socket; socket.gethostbyname(\"example.com\")'; elif command -v python >/dev/null 2>&1; then python -c 'import socket; socket.gethostbyname(\"example.com\")'; else exit 2; fi",
                ],
            )
            self.assertNotEqual(network_probe.returncode, 0)
            exec_result = docker_exec(docker, container_id, ["sh", "-lc", "printf ok >/workspace/result.txt; exit 0"])
            self.assertTrue(exec_result.succeeded)
            self.assertEqual((workspace / "result.txt").read_text(encoding="utf-8"), "ok")
            self.assertEqual(docker_cleanup_run(docker, "run-test"), 1)
            self.assertEqual(docker_list_containers(docker, run_id="run-test"), [])
        finally:
            docker_stop(docker, container_id)
            docker_remove(docker, container_id, force=True)

    def test_independent_verifier_stage_passes_and_cleans_up(self) -> None:
        docker = docker_executable()
        workspace, readonly, oracle, outside = temp_probe_dirs()
        _git(["init"], workspace)
        _git(["config", "user.email", "test@example.com"], workspace)
        _git(["config", "user.name", "Test User"], workspace)
        (workspace / "result.txt").write_text("OMA7_SYNTHETIC_EXECUTOR_OK", encoding="utf-8")
        _git(["add", "result.txt"], workspace)
        _git(["commit", "-m", "init"], workspace)
        frozen_identity, frozen_dir = freeze_snapshot(workspace)
        executor_spec = DockerContainerSpec(
            image_ref=PINNED_IMAGE,
            name="oma7-executor-stage",
            workspace_host_path=workspace,
            readonly_host_path=readonly,
            network="none",
            command=("sh", "-lc", "sleep 3600"),
        )
        executor_id = docker_create(docker, executor_spec, run_id="two-stage")
        docker_start(docker, executor_id)
        docker_stop(docker, executor_id)
        verifier = run_synthetic_verifier_stage(
            docker=docker,
            image_ref=PINNED_IMAGE,
            executor_container_id=executor_id,
            frozen_workspace=frozen_dir,
            oracle_workspace=oracle,
            verifier_identity="oma7-verifier",
            verifier_configuration_digest="sha256:verify-cfg",
            harness_commit_or_digest="harness-1",
            dataset_revision="dataset-1",
            oracle_test_patch_identity="oracle-1",
        )
        try:
            self.assertTrue(verifier.functional_pass)
            self.assertTrue(verifier.cleanup_proven)
            self.assertTrue(verifier.started_at)
            self.assertTrue(verifier.finished_at)
            self.assertTrue(verifier.image.digest)
            self.assertTrue(verifier.verification_context_identity.identity())
            self.assertEqual(verifier.stdout.strip(), "OMA7_SYNTHETIC_EXECUTOR_OK")
        finally:
            docker_remove(docker, executor_id, force=True)
        self.assertEqual(docker_list_containers(docker, run_id="two-stage"), [])

    def test_verifier_start_rejected_while_executor_active(self) -> None:
        docker = docker_executable()
        workspace, readonly, oracle, _ = temp_probe_dirs()
        _git(["init"], workspace)
        _git(["config", "user.email", "test@example.com"], workspace)
        _git(["config", "user.name", "Test User"], workspace)
        (workspace / "result.txt").write_text("OMA7_SYNTHETIC_EXECUTOR_OK", encoding="utf-8")
        _git(["add", "result.txt"], workspace)
        _git(["commit", "-m", "init"], workspace)
        frozen_identity, frozen_dir = freeze_snapshot(workspace)
        executor_spec = DockerContainerSpec(
            image_ref=PINNED_IMAGE,
            name="oma7-executor-active",
            workspace_host_path=workspace,
            readonly_host_path=readonly,
            network="none",
            command=("sh", "-lc", "sleep 3600"),
        )
        executor_id = docker_create(docker, executor_spec, run_id="active-run")
        docker_start(docker, executor_id)
        try:
            with self.assertRaises(RuntimeError):
                run_synthetic_verifier_stage(
                    docker=docker,
                    image_ref=PINNED_IMAGE,
                    executor_container_id=executor_id,
                    frozen_workspace=frozen_dir,
                    oracle_workspace=oracle,
                    verifier_identity="oma7-verifier",
                    verifier_configuration_digest="sha256:verify-cfg",
                    harness_commit_or_digest="harness-1",
                    dataset_revision="dataset-1",
                    oracle_test_patch_identity="oracle-1",
                )
        finally:
            docker_stop(docker, executor_id)
            docker_remove(docker, executor_id, force=True)

    def test_acceptance_and_scope_are_bound_to_verification_context(self) -> None:
        subject = SubjectIdentity(git_tree="tree-a", git_commit="commit-a", path="one")
        materialization = self.materialization(subject)
        execution = self.execution()
        verification = self.verification()
        scope_identity = self.scope_policy()
        provenance_inputs = ProvenanceAnchorInputs(
            subject_identity=subject,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            run_id="run-123",
            verifier_id="oma7-verifier",
            cost_ledger_head="ledger-1",
            cost_ledger_event_count=1,
            scope_decision=ScopeDecision.ALLOW,
            scope_change_id="change-1",
        )
        provenance = build_provenance_anchor(provenance_inputs)
        evidence = Evidence(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance.identity,
            result=ResultStatus.PASS,
            verifier_id="oma7-verifier",
            run_id="run-123",
        )
        scope_eval = evaluate_scope_change(
            self.scope_change(),
            self.scope_runtime_policy(),
            subject_identity=subject,
            materialization_identity=materialization,
        )
        observation = build_synthetic_acceptance_observation(
            evidence=evidence,
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance.identity,
            scope_evaluation=scope_eval,
        )
        decision = evaluate_acceptance(observation)
        self.assertEqual(decision.outcome.value, "EVAL_DONE")
        stale_observation = build_synthetic_acceptance_observation(
            evidence=evidence,
            subject_identity=SubjectIdentity(git_tree="tree-b", git_commit="commit-a", path="two"),
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance.identity,
            scope_evaluation=scope_eval,
        )
        self.assertEqual(evaluate_acceptance(stale_observation).outcome.value, "NOT_ACCEPTED")

    def test_provenance_binding_rejects_mismatches(self) -> None:
        subject = self.subject()
        materialization = self.materialization(subject)
        execution = self.execution()
        verification = self.verification()
        scope_identity = self.scope_policy()
        provenance = build_provenance_anchor(
            ProvenanceAnchorInputs(
                subject_identity=subject,
                execution_context_identity=execution,
                verification_context_identity=verification,
                scope_policy_identity=scope_identity,
                run_id="run-1",
                verifier_id="verifier-1",
                cost_ledger_head="ledger-1",
                cost_ledger_event_count=1,
                scope_decision=ScopeDecision.ALLOW,
                scope_change_id="change-1",
            )
        )
        evidence = Evidence(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance.identity,
            result=ResultStatus.PASS,
            verifier_id="verifier-1",
            run_id="run-1",
        )
        scope_eval = evaluate_scope_change(
            self.scope_change(),
            self.scope_runtime_policy(),
            subject_identity=subject,
            materialization_identity=materialization,
        )
        ok = build_synthetic_acceptance_observation(
            evidence=evidence,
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance.identity,
            scope_evaluation=scope_eval,
        )
        self.assertEqual(evaluate_acceptance(ok).outcome.value, "EVAL_DONE")
        self.assertEqual(
            evaluate_acceptance(
                build_synthetic_acceptance_observation(
                    evidence=evidence,
                    subject_identity=self.subject(),
                    materialization_identity=materialization,
                    execution_context_identity=execution,
                    verification_context_identity=verification,
                    scope_policy_identity=scope_identity,
                    provenance_anchor_identity=build_provenance_anchor(
                        ProvenanceAnchorInputs(
                            subject_identity=subject,
                            execution_context_identity=execution,
                            verification_context_identity=verification,
                            scope_policy_identity=scope_identity,
                            run_id="run-2",
                            verifier_id="verifier-1",
                            cost_ledger_head="ledger-1",
                            cost_ledger_event_count=1,
                            scope_decision=ScopeDecision.ALLOW,
                            scope_change_id="change-1",
                        )
                    ).identity,
                    scope_evaluation=scope_eval,
                )
            ).outcome.value,
            "NOT_ACCEPTED",
        )

    def test_stale_evidence_rejected_after_mutation(self) -> None:
        subject = self.subject()
        materialization = self.materialization(subject)
        execution = self.execution()
        verification = self.verification()
        scope_identity = self.scope_policy()
        provenance = build_provenance_anchor(
            ProvenanceAnchorInputs(
                subject_identity=subject,
                execution_context_identity=execution,
                verification_context_identity=verification,
                scope_policy_identity=scope_identity,
                run_id="run-stale",
                verifier_id="verifier-1",
                cost_ledger_head="ledger-1",
                cost_ledger_event_count=1,
                scope_decision=ScopeDecision.ALLOW,
                scope_change_id="change-1",
            )
        )
        evidence = Evidence(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance.identity,
            result=ResultStatus.PASS,
            verifier_id="verifier-1",
            run_id="run-stale",
        )
        scope_eval = evaluate_scope_change(
            self.scope_change(),
            self.scope_runtime_policy(),
            subject_identity=subject,
            materialization_identity=materialization,
        )
        mutated_subject = self.subject()
        mutated_subject = SubjectIdentity(git_tree="tree-mutated", git_commit="commit", path=".")
        self.assertEqual(
            evaluate_acceptance(
                build_synthetic_acceptance_observation(
                    evidence=evidence,
                    subject_identity=mutated_subject,
                    materialization_identity=materialization,
                    execution_context_identity=execution,
                    verification_context_identity=verification,
                    scope_policy_identity=scope_identity,
                    provenance_anchor_identity=provenance.identity,
                    scope_evaluation=scope_eval,
                )
            ).outcome.value,
            "NOT_ACCEPTED",
        )
        self.assertEqual(
            evaluate_acceptance(
                build_synthetic_acceptance_observation(
                    evidence=evidence,
                    subject_identity=subject,
                    materialization_identity=materialization,
                    execution_context_identity=self.execution("env-different"),
                    verification_context_identity=verification,
                    scope_policy_identity=scope_identity,
                    provenance_anchor_identity=provenance.identity,
                    scope_evaluation=scope_eval,
                )
            ).outcome.value,
            "NOT_ACCEPTED",
        )

    def test_freeze_requires_quiescence_and_uses_independent_copy(self) -> None:
        docker = docker_executable()
        workspace, readonly, _, _ = temp_probe_dirs()
        _git(["init"], workspace)
        _git(["config", "user.email", "test@example.com"], workspace)
        _git(["config", "user.name", "Test User"], workspace)
        (workspace / "tracked.txt").write_text("one\n", encoding="utf-8")
        _git(["add", "tracked.txt"], workspace)
        _git(["commit", "-m", "init"], workspace)
        spec = DockerContainerSpec(
            image_ref=PINNED_IMAGE,
            name="oma7-freeze-test",
            workspace_host_path=workspace,
            readonly_host_path=readonly,
            network="none",
            command=("sh", "-lc", "sleep 3600"),
        )
        container_id = docker_create(docker, spec, run_id="freeze-run")
        docker_start(docker, container_id)
        try:
            with self.assertRaises(RuntimeError):
                ensure_container_quiescent(docker, container_id)
            docker_stop(docker, container_id)
            frozen_identity, frozen_dir = freeze_workspace_after_quiescence(docker, container_id, workspace)
            self.assertTrue(verify_snapshot_is_copy(frozen_dir, workspace))
            self.assertTrue(frozen_identity.identity())
            (workspace / "tracked.txt").write_text("two\n", encoding="utf-8")
            self.assertNotEqual((frozen_dir / "tracked.txt").read_text(encoding="utf-8"), (workspace / "tracked.txt").read_text(encoding="utf-8"))
        finally:
            docker_remove(docker, container_id, force=True)


if __name__ == "__main__":
    unittest.main()
