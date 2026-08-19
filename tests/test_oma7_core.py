from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.git_identity import compute_git_tree_identity
from oma7.lifecycle import (
    AcceptanceOutcome,
    AtomicEvidencePublicationResult,
    ControlledLifecycleObservation,
    GateStatus,
    LifecycleState,
    ResumeClassification,
    RunIdentity,
    DurableRunRecord,
    evidence_publication_payload,
    load_durable_run_record,
    load_published_evidence,
    evaluate_acceptance,
    finalize_durable_done,
    publish_atomic_evidence,
    write_durable_run_record,
)
from oma7.models import (
    Evidence,
    ExecutionContextIdentity,
    MaterializationIdentity,
    ProvenanceAnchorIdentity,
    ResultStatus,
    ScopePolicyIdentity,
    SubjectIdentity,
    VerificationContextIdentity,
)
from oma7.qualifier import qualify_observation
from oma7.snapshot import freeze_snapshot
from oma7.swebench_adapter import normalize_b0_observation
from oma7.swebench_contract import effective_model_patch
from oma7.verifier import verify_evidence, verify_snapshot_is_copy


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(["git", *cmd], cwd=cwd, check=True, capture_output=True, text=True)


class Oma7CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        _git(["init"], self.repo)
        _git(["config", "user.email", "test@example.com"], self.repo)
        _git(["config", "user.name", "Test User"], self.repo)
        (self.repo / "tracked.txt").write_text("one\n", encoding="utf-8")
        _git(["add", "tracked.txt"], self.repo)
        _git(["commit", "-m", "init"], self.repo)

    def subject(self) -> SubjectIdentity:
        return SubjectIdentity(git_tree="tree", git_commit="commit", path=".")

    def materialization(self, subject: SubjectIdentity | None = None) -> MaterializationIdentity:
        subject = subject or self.subject()
        return MaterializationIdentity(
            subject_identity=subject,
            canonical_root_descriptor="git:root",
            symlink_topology=(("a", "b"),),
            hardlink_topology=(("c", "d"),),
            worktree_reference_identity="worktree-1",
            mounted_reference_artifact_identities=("ref-1",),
            cache_manifest_digest="cache-1",
        )

    def execution(self, digest: str = "env-digest") -> ExecutionContextIdentity:
        return ExecutionContextIdentity(
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

    def verification(self, revision: str = "dataset-1", oracle: str = "oracle-1") -> VerificationContextIdentity:
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

    def scope_policy(self, scope_budget: str = "budget-1", exceptions: tuple[str, ...] = ("exc-1",)) -> ScopePolicyIdentity:
        return ScopePolicyIdentity(
            allowed_scope_path_policy=("src/**", "tests/**"),
            protected_semantic_roles=("oracle", "provenance"),
            explicit_sensitive_change_authorizations=("manifest",),
            scope_budget=scope_budget,
            task_specific_exceptions=exceptions,
            rule_schema_version="scope/v1",
        )

    def provenance(self, digest: str = "anchor-1", root: str = "root-1") -> ProvenanceAnchorIdentity:
        return ProvenanceAnchorIdentity(
            anchor_type="in-toto",
            immutable_anchor_identifier_digest=digest,
            provenance_root=root,
            event_count=3,
            schema_information="prov/v1",
        )

    def evidence(self, **overrides) -> Evidence:
        base = dict(
            subject_identity=self.subject(),
            materialization_identity=self.materialization(),
            execution_context_identity=self.execution(),
            verification_context_identity=self.verification(),
            scope_policy_identity=self.scope_policy(),
            provenance_anchor_identity=self.provenance(),
            result=ResultStatus.PASS,
            schema_version="oma7.evidence/v1",
        )
        base.update(overrides)
        return Evidence(**base)

    def observation(self, **overrides) -> ControlledLifecycleObservation:
        base = dict(
            executor_state=LifecycleState.FROZEN,
            lifecycle_state=LifecycleState.VERIFICATION_PENDING,
            verifier_result=ResultStatus.PASS,
            evidence=self.evidence(),
            subject_identity=self.subject(),
            materialization_identity=self.materialization(),
            execution_context_identity=self.execution(),
            verification_context_identity=self.verification(),
            scope_policy_identity=self.scope_policy(),
            provenance_anchor_identity=self.provenance(),
            quiescence_status=GateStatus.PASS_,
            freeze_status=GateStatus.PASS_,
            integrity_status=GateStatus.PASS_,
            no_op_precheck_status=GateStatus.NOT_IMPLEMENTED,
            no_op_expected_unchanged=None,
            metadata={},
        )
        base.update(overrides)
        return ControlledLifecycleObservation(**base)

    def run_identity(self) -> RunIdentity:
        return RunIdentity(
            instance_id="instance-1",
            phase="phase-1",
            replicate="replicate-1",
            subject_identity=self.subject(),
            materialization_identity=self.materialization(),
            execution_context_identity=self.execution(),
            verification_context_identity=self.verification(),
            scope_policy_identity=self.scope_policy(),
            provenance_anchor_identity=self.provenance(),
        )

    def test_git_identity_changes_on_content_mutation(self) -> None:
        base = compute_git_tree_identity(self.repo)
        (self.repo / "tracked.txt").write_text("two\n", encoding="utf-8")
        changed = compute_git_tree_identity(self.repo)
        self.assertNotEqual(base, changed)

    def test_snapshot_is_copy_and_stable(self) -> None:
        snapshot, frozen_dir = freeze_snapshot(self.repo)
        self.assertTrue(verify_snapshot_is_copy(frozen_dir, self.repo))
        before = snapshot.identity()
        (self.repo / "tracked.txt").write_text("mutated\n", encoding="utf-8")
        after, _ = freeze_snapshot(self.repo)
        self.assertNotEqual(before, after.identity())

    def test_same_subject_context_accepts(self) -> None:
        evidence = self.evidence()
        applicability = verify_evidence(
            evidence,
            self.subject(),
            self.materialization(),
            self.execution(),
            self.verification(),
            self.scope_policy(),
            self.provenance(),
            ResultStatus.PASS,
        )
        self.assertTrue(applicability.authorizes_acceptance)

    def test_adversarial_mutations_reject(self) -> None:
        evidence = self.evidence()
        base_subject = self.subject()
        base_materialization = self.materialization()
        base_execution = self.execution()
        base_verification = self.verification()
        base_scope = self.scope_policy()
        base_provenance = self.provenance()
        cases = [
            ("subject same / materialization changed", base_subject, self.materialization(subject=SubjectIdentity(git_tree="tree-x", git_commit="commit", path=".")), base_execution, base_verification, base_scope, base_provenance, ResultStatus.PASS),
            ("subject/materialization same / execution changed", base_subject, base_materialization, self.execution("env-digest-x"), base_verification, base_scope, base_provenance, ResultStatus.PASS),
            ("verification changed", base_subject, base_materialization, base_execution, self.verification(revision="dataset-2"), base_scope, base_provenance, ResultStatus.PASS),
            ("scope changed", base_subject, base_materialization, base_execution, base_verification, self.scope_policy(scope_budget="budget-2"), base_provenance, ResultStatus.PASS),
            ("provenance changed", base_subject, base_materialization, base_execution, base_verification, base_scope, self.provenance(digest="anchor-2"), ResultStatus.PASS),
            ("fail result", base_subject, base_materialization, base_execution, base_verification, base_scope, base_provenance, ResultStatus.FAIL),
            ("anchor root mismatch", base_subject, base_materialization, base_execution, base_verification, base_scope, self.provenance(root="root-2"), ResultStatus.PASS),
        ]
        for name, subject, materialization, execution, verification, scope, provenance, result in cases:
            with self.subTest(name=name):
                applicability = verify_evidence(
                    evidence,
                    subject,
                    materialization,
                    execution,
                    verification,
                    scope,
                    provenance,
                    result,
                )
                self.assertFalse(applicability.authorizes_acceptance)

    def test_missing_mandatory_identity_fails_closed(self) -> None:
        evidence = Evidence(
            subject_identity=None,
            materialization_identity=self.materialization(),
            execution_context_identity=self.execution(),
            verification_context_identity=self.verification(),
            scope_policy_identity=self.scope_policy(),
            provenance_anchor_identity=self.provenance(),
            result=ResultStatus.PASS,
            schema_version="oma7.evidence/v1",
        )
        applicability = verify_evidence(
            evidence,
            self.subject(),
            self.materialization(),
            self.execution(),
            self.verification(),
            self.scope_policy(),
            self.provenance(),
            ResultStatus.PASS,
        )
        self.assertFalse(applicability.authorizes_acceptance)

    def test_unsupported_schema_fails_closed(self) -> None:
        evidence = self.evidence(schema_version="oma7.evidence/v9")
        applicability = verify_evidence(
            evidence,
            self.subject(),
            self.materialization(),
            self.execution(),
            self.verification(),
            self.scope_policy(),
            self.provenance(),
            ResultStatus.PASS,
        )
        self.assertFalse(applicability.authorizes_acceptance)

    def test_canonicalization_dict_ordering(self) -> None:
        evidence_a = self.evidence(predicate={"alpha": 1, "beta": {"x": 2, "y": 3}})
        evidence_b = self.evidence(predicate={"beta": {"y": 3, "x": 2}, "alpha": 1})
        self.assertEqual(evidence_a.identity(), evidence_b.identity())

    def test_canonicalization_semantic_change(self) -> None:
        policy_a = self.scope_policy()
        policy_b = self.scope_policy(scope_budget="budget-2")
        self.assertNotEqual(policy_a.identity(), policy_b.identity())

    def test_regular_file_vs_symlink_materialization_differs(self) -> None:
        subject = self.subject()
        file_materialization = MaterializationIdentity(
            subject_identity=subject,
            canonical_root_descriptor="root",
            symlink_topology=(),
            hardlink_topology=(),
            worktree_reference_identity="worktree-1",
            mounted_reference_artifact_identities=(),
            cache_manifest_digest="cache-1",
        )
        symlink_materialization = MaterializationIdentity(
            subject_identity=subject,
            canonical_root_descriptor="root",
            symlink_topology=(("a", "b"),),
            hardlink_topology=(),
            worktree_reference_identity="worktree-1",
            mounted_reference_artifact_identities=(),
            cache_manifest_digest="cache-1",
        )
        self.assertNotEqual(file_materialization.identity(), symlink_materialization.identity())

    def test_cache_manifest_digest_changes_identity(self) -> None:
        subject = self.subject()
        m1 = MaterializationIdentity(subject, "root", cache_manifest_digest="cache-1")
        m2 = MaterializationIdentity(subject, "root", cache_manifest_digest="cache-2")
        self.assertNotEqual(m1.identity(), m2.identity())

    def test_nominal_image_tag_same_but_digest_different(self) -> None:
        e1 = self.execution("sha256:a")
        e2 = self.execution("sha256:b")
        self.assertNotEqual(e1.identity(), e2.identity())

    def test_normalizer_and_qualifier(self) -> None:
        obs = normalize_b0_observation(
            {
                "schema_version": "oma7.evidence/v1",
                "subject_identity": {
                    "git_tree": "tree",
                    "git_commit": "commit",
                    "path": ".",
                },
                "materialization_identity": {
                    "canonical_root_descriptor": "git:root",
                    "symlink_topology": [],
                    "hardlink_topology": [],
                    "worktree_reference_identity": "worktree-1",
                    "mounted_reference_artifact_identities": [],
                    "cache_manifest_digest": "cache-1",
                },
                "execution_context_identity": {
                    "environment_container_image_digest": "sha256:a",
                    "codex_binary_digest": "codex-bin",
                    "codex_version": "0.1.0",
                    "model": "o-model",
                    "reasoning_level": "high",
                    "harness_commit_or_digest": "harness-1",
                    "harness_configuration_digest": "cfg-1",
                    "dependency_lock_digest": "lock-1",
                    "dataset_revision": "dataset-1",
                    "toolchain_identity": "toolchain-1",
                },
                "verification_context_identity": {
                    "dataset_revision": "dataset-1",
                    "oracle_test_patch_identity": "oracle-1",
                    "fail_to_pass": ["f1"],
                    "pass_to_pass": ["p1"],
                    "harness_commit_or_digest": "harness-1",
                    "verification_configuration_digest": "verify-cfg-1",
                    "verifier_environment_image_digest": "verifier-img-1",
                    "verifier_identity": "verifier-1",
                },
                "scope_policy_identity": {
                    "allowed_scope_path_policy": ["src/**"],
                    "protected_semantic_roles": ["oracle"],
                    "explicit_sensitive_change_authorizations": ["manifest"],
                    "scope_budget": "budget-1",
                    "task_specific_exceptions": ["exc-1"],
                    "rule_schema_version": "scope/v1",
                },
                "provenance_anchor_identity": {
                    "anchor_type": "in-toto",
                    "immutable_anchor_identifier_digest": "anchor-1",
                    "provenance_root": "root-1",
                    "event_count": 3,
                    "schema_information": "prov/v1",
                },
                "result": "PASS",
                "tests_status": {"test_a": "FAIL"},
            }
        )
        self.assertEqual(obs.result, ResultStatus.PASS)
        self.assertEqual(qualify_observation(obs).value, "QUALIFIED")

    def test_missing_schema_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            normalize_b0_observation({"result": "PASS"})

    def test_unsupported_schema_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            normalize_b0_observation({"schema_version": "oma7.evidence/v9", "result": "PASS"})

    def test_unsupported_enum_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            normalize_b0_observation(
                {
                    "schema_version": "oma7.evidence/v1",
                    "subject_identity": {"git_tree": "tree"},
                    "materialization_identity": {"canonical_root_descriptor": "root"},
                    "execution_context_identity": {
                        "environment_container_image_digest": "sha256:a",
                        "codex_binary_digest": "codex-bin",
                        "codex_version": "0.1.0",
                        "model": "o-model",
                        "reasoning_level": "high",
                        "harness_commit_or_digest": "harness-1",
                        "harness_configuration_digest": "cfg-1",
                        "dependency_lock_digest": "lock-1",
                        "dataset_revision": "dataset-1",
                        "toolchain_identity": "toolchain-1",
                    },
                    "verification_context_identity": {
                        "dataset_revision": "dataset-1",
                        "oracle_test_patch_identity": "oracle-1",
                        "fail_to_pass": [],
                        "pass_to_pass": [],
                        "harness_commit_or_digest": "harness-1",
                        "verification_configuration_digest": "verify-cfg-1",
                    },
                    "scope_policy_identity": {
                        "allowed_scope_path_policy": [],
                        "protected_semantic_roles": [],
                        "explicit_sensitive_change_authorizations": [],
                        "scope_budget": "budget-1",
                        "task_specific_exceptions": [],
                        "rule_schema_version": "scope/v1",
                    },
                    "provenance_anchor_identity": {
                        "anchor_type": "in-toto",
                        "immutable_anchor_identifier_digest": "anchor-1",
                        "provenance_root": "root-1",
                    },
                    "result": "TOTALLY_UNKNOWN",
                }
            )

    def test_skip_patch_ignores_prediction_patch(self) -> None:
        self.assertEqual(effective_model_patch({"model_patch": "diff --git a b"}, skip_patch=True), "")
        self.assertEqual(
            effective_model_patch({"model_patch": "diff --git a b"}, skip_patch=False),
            "diff --git a b",
        )

    def test_false_done_final_message_only_rejects(self) -> None:
        decision = evaluate_acceptance(
            self.observation(
                evidence=None,
                verifier_result=ResultStatus.PASS,
                lifecycle_state=LifecycleState.EXECUTOR_TERMINATED,
                executor_state=LifecycleState.EXECUTOR_TERMINATED,
            )
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_false_done_exit_zero_only_rejects(self) -> None:
        decision = evaluate_acceptance(
            self.observation(
                evidence=None,
                lifecycle_state=LifecycleState.EXECUTOR_TERMINATED,
                executor_state=LifecycleState.EXECUTOR_TERMINATED,
            )
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_false_done_terminal_executor_event_only_rejects(self) -> None:
        decision = evaluate_acceptance(
            self.observation(
                evidence=None,
                lifecycle_state=LifecycleState.EXECUTOR_TERMINATED,
                executor_state=LifecycleState.EXECUTOR_TERMINATED,
            )
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_false_done_verifier_pass_stale_evidence_rejects(self) -> None:
        decision = evaluate_acceptance(
            self.observation(
                evidence=self.evidence(
                    subject_identity=self.subject(),
                    materialization_identity=self.materialization(
                        subject=SubjectIdentity(git_tree="tree-x", git_commit="commit", path=".")
                    ),
                )
            )
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_false_done_unsupported_schema_rejects(self) -> None:
        decision = evaluate_acceptance(self.observation(evidence=self.evidence(schema_version="oma7.evidence/v9")))
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_false_done_missing_required_identity_rejects(self) -> None:
        decision = evaluate_acceptance(self.observation(subject_identity=None))
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_false_done_unknown_gate_rejects(self) -> None:
        decision = evaluate_acceptance(self.observation(quiescence_status=GateStatus.UNKNOWN))
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_false_done_applicable_pass_evidence_accepts(self) -> None:
        decision = evaluate_acceptance(self.observation())
        self.assertEqual(decision.outcome, AcceptanceOutcome.EVAL_DONE)

    def test_noop_claim_without_positive_verification_rejects(self) -> None:
        decision = evaluate_acceptance(
            self.observation(
                no_op_precheck_status=GateStatus.PASS_,
                no_op_expected_unchanged=None,
            )
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_verified_legitimate_noop_accepts(self) -> None:
        decision = evaluate_acceptance(
            self.observation(
                no_op_precheck_status=GateStatus.PASS_,
                no_op_expected_unchanged=True,
            )
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NO_OP)

    def test_noop_unexpected_mutation_rejects_review(self) -> None:
        decision = evaluate_acceptance(
            self.observation(
                no_op_precheck_status=GateStatus.PASS_,
                no_op_expected_unchanged=False,
            )
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)
        self.assertEqual(decision.lifecycle_state, LifecycleState.REVIEW_REQUIRED)

    def test_timeout_candidate_patch_not_done(self) -> None:
        decision = evaluate_acceptance(
            self.observation(
                lifecycle_state=LifecycleState.RETRY_REQUIRED,
                executor_state=LifecycleState.EXECUTOR_TERMINATED,
            )
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_timeout_previous_pass_evidence_not_applicable_not_done(self) -> None:
        decision = evaluate_acceptance(
            self.observation(
                evidence=self.evidence(
                    subject_identity=self.subject(),
                    materialization_identity=self.materialization(
                        subject=SubjectIdentity(git_tree="tree-z", git_commit="commit", path=".")
                    ),
                )
            )
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_recovered_subject_fresh_applicable_evidence_may_complete(self) -> None:
        decision = evaluate_acceptance(self.observation())
        self.assertEqual(decision.lifecycle_state, LifecycleState.EVAL_DONE)

    def test_retry_required_executor_message_stays_retry(self) -> None:
        decision = evaluate_acceptance(
            self.observation(lifecycle_state=LifecycleState.RETRY_REQUIRED)
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)
        self.assertEqual(decision.lifecycle_state, LifecycleState.RETRY_REQUIRED)

    def test_review_required_metadata_only_update_stays_review(self) -> None:
        decision = evaluate_acceptance(
            self.observation(lifecycle_state=LifecycleState.REVIEW_REQUIRED)
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)
        self.assertEqual(decision.lifecycle_state, LifecycleState.REVIEW_REQUIRED)

    def test_blocked_policy_resolution_only_not_done(self) -> None:
        decision = evaluate_acceptance(
            self.observation(lifecycle_state=LifecycleState.BLOCKED)
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_blocked_resolution_and_fresh_evidence_may_complete(self) -> None:
        decision = evaluate_acceptance(self.observation())
        self.assertEqual(decision.outcome, AcceptanceOutcome.EVAL_DONE)

    def test_missing_mandatory_observation_fails_closed(self) -> None:
        decision = evaluate_acceptance(self.observation(quiescence_status=GateStatus.NOT_IMPLEMENTED))
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_unknown_enum_fails_closed(self) -> None:
        decision = evaluate_acceptance(self.observation(quiescence_status=GateStatus.UNKNOWN))
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_integrity_inspection_error_fails_closed(self) -> None:
        decision = evaluate_acceptance(self.observation(integrity_status=GateStatus.FAIL))
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_atomic_publication_temp_only_unpublished(self) -> None:
        target = self.repo / "evidence.json"
        result = publish_atomic_evidence(target, {"a": 1})
        self.assertTrue(result.published)
        self.assertTrue(target.exists())

    def test_atomic_publication_truncated_invalid(self) -> None:
        target = self.repo / "truncated.json"
        target.write_text("{", encoding="utf-8")
        self.assertIsNone(load_published_evidence(target))

    def test_atomic_publication_identical_replay_idempotent(self) -> None:
        target = self.repo / "replay.json"
        first = publish_atomic_evidence(target, {"x": 1})
        second = publish_atomic_evidence(target, {"x": 1})
        self.assertTrue(first.published)
        self.assertTrue(second.published)
        self.assertFalse(second.conflict)

    def test_atomic_publication_conflicting_replay_conflict(self) -> None:
        target = self.repo / "conflict.json"
        first = publish_atomic_evidence(target, {"x": 1})
        second = publish_atomic_evidence(target, {"x": 2})
        self.assertTrue(first.published)
        self.assertTrue(second.conflict)

    def test_evidence_published_done_missing_resumable(self) -> None:
        target = self.repo / "resume.json"
        result = publish_atomic_evidence(target, {"x": 1})
        self.assertTrue(result.published)
        self.assertTrue(target.exists())
        self.assertEqual(load_published_evidence(target), {"x": 1})

    def test_done_present_evidence_missing_invalid_terminal(self) -> None:
        self.assertFalse((self.repo / "missing.json").exists())

    def test_evidence_identity_mismatch_on_resume_not_done(self) -> None:
        decision = evaluate_acceptance(
            self.observation(
                evidence=self.evidence(subject_identity=SubjectIdentity(git_tree="other", git_commit="commit", path=".")),
            )
        )
        self.assertEqual(decision.outcome, AcceptanceOutcome.NOT_ACCEPTED)

    def test_atomic_publication_succeeds_and_applicable_evidence_validates(self) -> None:
        target = self.repo / "final.json"
        result = publish_atomic_evidence(target, {"run_id": "1", "result": "PASS"})
        self.assertTrue(result.published)
        self.assertTrue(target.exists())

    def test_durable_run_record_writes_and_loads(self) -> None:
        path = self.repo / "run.json"
        record = DurableRunRecord(
            schema_version="oma7.run-record/v1",
            run_identity=self.run_identity(),
            lifecycle_state=LifecycleState.VERIFICATION_PENDING,
            evidence_reference="evidence.json",
            evidence_identity="abc123",
            durability={
                "file_fsync_performed": True,
                "directory_fsync_performed": False,
                "atomic_replace_used": True,
            },
        )
        result = write_durable_run_record(path, record)
        self.assertTrue(result.atomic_replace_used)
        loaded = load_durable_run_record(path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["schema_version"], "oma7.run-record/v1")
        self.assertEqual(loaded["lifecycle_state"], "VERIFICATION_PENDING")

    def test_crash_before_evidence_temp_write_not_done(self) -> None:
        run_record_path = self.repo / "run.json"
        self.assertEqual(
            finalize_durable_done(run_record_path, self.repo / "evidence.json", self.run_identity(), self.observation()),
            ResumeClassification.INVALID,
        )

    def test_crash_after_temp_write_before_replace_not_done(self) -> None:
        run_record_path = self.repo / "run.json"
        evidence_path = self.repo / "evidence.json.tmp"
        evidence_path.write_text("{", encoding="utf-8")
        self.assertEqual(
            finalize_durable_done(run_record_path, evidence_path, self.run_identity(), self.observation()),
            ResumeClassification.INVALID,
        )

    def test_evidence_published_without_terminal_is_resumable(self) -> None:
        run_record_path = self.repo / "run.json"
        evidence_path = self.repo / "evidence.json"
        publish_atomic_evidence(evidence_path, evidence_publication_payload(self.evidence()))
        self.assertEqual(
            finalize_durable_done(run_record_path, evidence_path, self.run_identity(), self.observation()),
            ResumeClassification.DONE,
        )

    def test_done_present_evidence_missing_invalid(self) -> None:
        run_record_path = self.repo / "run.json"
        write_durable_run_record(
            run_record_path,
            DurableRunRecord(
                schema_version="oma7.run-record/v1",
                run_identity=self.run_identity(),
                lifecycle_state=LifecycleState.EVAL_DONE,
                evidence_reference="evidence.json",
                evidence_identity="abc123",
                durability={
                    "file_fsync_performed": True,
                    "directory_fsync_performed": False,
                    "atomic_replace_used": True,
                },
            ),
        )
        self.assertEqual(
            finalize_durable_done(run_record_path, self.repo / "missing.json", self.run_identity(), self.observation()),
            ResumeClassification.INVALID,
        )

    def test_done_present_malformed_evidence_invalid(self) -> None:
        run_record_path = self.repo / "run.json"
        write_durable_run_record(
            run_record_path,
            DurableRunRecord(
                schema_version="oma7.run-record/v1",
                run_identity=self.run_identity(),
                lifecycle_state=LifecycleState.EVAL_DONE,
                evidence_reference="evidence.json",
                evidence_identity="abc123",
                durability={
                    "file_fsync_performed": True,
                    "directory_fsync_performed": False,
                    "atomic_replace_used": True,
                },
            ),
        )
        evidence_path = self.repo / "evidence.json"
        evidence_path.write_text("{", encoding="utf-8")
        self.assertEqual(
            finalize_durable_done(run_record_path, evidence_path, self.run_identity(), self.observation()),
            ResumeClassification.INVALID,
        )

    def test_done_present_identity_mismatch_invalid(self) -> None:
        run_record_path = self.repo / "run.json"
        evidence_path = self.repo / "evidence.json"
        publish_atomic_evidence(evidence_path, {"schema_version": "oma7.evidence/v1", "a": 1})
        write_durable_run_record(
            run_record_path,
            DurableRunRecord(
                schema_version="oma7.run-record/v1",
                run_identity=self.run_identity(),
                lifecycle_state=LifecycleState.EVAL_DONE,
                evidence_reference="evidence.json",
                evidence_identity="different",
                durability={
                    "file_fsync_performed": True,
                    "directory_fsync_performed": False,
                    "atomic_replace_used": True,
                },
            ),
        )
        self.assertEqual(
            finalize_durable_done(run_record_path, evidence_path, self.run_identity(), self.observation()),
            ResumeClassification.INVALID,
        )

    def test_unsupported_run_record_schema_fails_closed(self) -> None:
        path = self.repo / "run.json"
        path.write_text(json.dumps({"schema_version": "oma7.run-record/v9"}), encoding="utf-8")
        self.assertIsNone(load_durable_run_record(path))

    def test_valid_evidence_and_pending_lifecycle_finalize_idempotently(self) -> None:
        run_record_path = self.repo / "run.json"
        evidence_path = self.repo / "evidence.json"
        evidence = self.evidence()
        publish_atomic_evidence(evidence_path, evidence_publication_payload(evidence))
        self.assertEqual(
            finalize_durable_done(run_record_path, evidence_path, self.run_identity(), self.observation()),
            ResumeClassification.DONE,
        )




if __name__ == "__main__":
    unittest.main()
