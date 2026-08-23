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
from oma7.scope import (
    ScopeChange,
    ScopeDecision,
    ScopeMutationKind,
    ScopeObjectType,
    ScopeOperation,
    ProvenanceAnchorInputs,
    ScopePolicy,
    build_provenance_anchor,
    canonicalize_scope_path,
    evaluate_scope_change,
)
from oma7.preflight import (
    PreflightResult,
    ProductionPreflightConfig,
    ProductionPreflightResult,
    RuntimePins,
    SandboxPreflightConfig,
    execution_context_id_from_pins,
    execution_context_identity_from_pins,
    make_dry_run_plan,
    run_sandbox_preflight,
    run_production_preflight,
)
from oma7.evidence_ledger import append_evidence, load_evidence
from oma7.models import (
    Evidence,
    ExecutionContextIdentity,
    compute_mission_identity,
    MaterializationIdentity,
    ProvenanceAnchorIdentity,
    ResultStatus,
    ScopePolicyIdentity,
    SubjectIdentity,
    VerificationContextIdentity,
)
from oma7.control_plane import (
    RetryBudget,
    bind_control_record,
    can_start_attempt,
    create_control_record as _create_control_record,
    load_control_record,
    validate_control_record,
    write_control_record,
    new_attempt_identity,
    control_policy_identity_from_policy,
    FailureClassification,
    EscalationReason,
)
from oma7.qualifier import qualify_observation
from oma7.snapshot import freeze_snapshot
from oma7.swebench_adapter import normalize_b0_observation
from oma7.swebench_contract import effective_model_patch
from oma7.verifier import verify_evidence, verify_snapshot_is_copy



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

    def scope_runtime_policy(self, allowed: tuple[str, ...] = ("allowed/**", "generated/**", "tests/**")) -> ScopePolicy:
        return ScopePolicy(allowed_scope_path_policy=allowed)

    def scope_change(self, **overrides) -> ScopeChange:
        base = dict(
            operation=ScopeOperation.MODIFY,
            before_path="allowed/file.txt",
            after_path="allowed/file.txt",
            before_object_type=ScopeObjectType.FILE,
            after_object_type=ScopeObjectType.FILE,
            before_identity="before-1",
            after_identity="after-1",
            mutation_kind=ScopeMutationKind.PRIMARY,
            parent_change_id=None,
            explicitly_allowed=False,
            change_id="change-1",
        )
        base.update(overrides)
        return ScopeChange(**base)

    def scope_evaluation(self, subject: SubjectIdentity | None = None, materialization: MaterializationIdentity | None = None, **change_overrides):
        subject = subject or self.subject()
        materialization = materialization or self.materialization(subject)
        return evaluate_scope_change(
            self.scope_change(**change_overrides),
            self.scope_runtime_policy(),
            subject_identity=subject,
            materialization_identity=materialization,
            authorized_primary_change_ids=("primary-1",),
        )

    def provenance(self, digest: str = "anchor-1", root: str = "root-1") -> ProvenanceAnchorIdentity:
        return ProvenanceAnchorIdentity(
            anchor_type="in-toto",
            immutable_anchor_identifier_digest=digest,
            provenance_root=root,
            event_count=3,
            schema_information="prov/v1",
        )

    def provenance_inputs(
        self,
        subject: SubjectIdentity | None = None,
        execution: ExecutionContextIdentity | None = None,
        verification: VerificationContextIdentity | None = None,
        scope_policy: ScopePolicyIdentity | None = None,
        **overrides,
    ) -> ProvenanceAnchorInputs:
        base = dict(
            subject_identity=subject or self.subject(),
            execution_context_identity=execution or self.execution(),
            verification_context_identity=verification or self.verification(),
            scope_policy_identity=scope_policy or self.scope_policy(),
            run_id="run-1",
            verifier_id="verifier-1",
            cost_ledger_head="ledger-1",
            cost_ledger_event_count=3,
            scope_decision=ScopeDecision.ALLOW,
            scope_change_id="change-1",
        )
        base.update(overrides)
        return ProvenanceAnchorInputs(**base)

    def provenance_anchor(self, **overrides):
        return build_provenance_anchor(self.provenance_inputs(**overrides))

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
            scope_evaluation=self.scope_evaluation(),
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

    def runtime_pins(self, **overrides) -> RuntimePins:
        base = dict(
            codex_sha256="6ee176b43f96b2294c8e2265d599f829e161b2c2ad34cb2b8fbf5f836fd34b8c",
            codex_version="0.1.0",
            model="o-model",
            reasoning_level="high",
            harness_commit_or_digest="8be9acebf1387b0fe0abdfdce8bb2ef9a2c0ac50",
            harness_configuration_digest="sha256:1111111111111111111111111111111111111111111111111111111111111111",
            dataset_revision="sha256:2222222222222222222222222222222222222222222222222222222222222222",
            dependency_lock_digest="sha256:3333333333333333333333333333333333333333333333333333333333333333",
            container_image_digest="sha256:4444444444444444444444444444444444444444444444444444444444444444",
            toolchain_identity="sha256:5555555555555555555555555555555555555555555555555555555555555555",
        )
        base.update(overrides)
        return RuntimePins(**base)

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

    def test_subject_identity_is_logical_and_frozen(self) -> None:
        subject_a = self.subject()
        subject_b = SubjectIdentity(git_tree="tree-2", git_commit="commit", path=".")
        self.assertNotEqual(subject_a.identity(), subject_b.identity())
        self.assertEqual(subject_a.identity(), SubjectIdentity(git_tree="tree", git_commit="commit", path="different/workspace").identity())
        self.assertEqual(subject_a.identity(), SubjectIdentity(git_tree="tree", git_commit="commit", path="C:/tmp/oma7-checkout").identity())

    def test_subject_identity_is_unchanged_by_other_contexts(self) -> None:
        subject = self.subject()
        materialization_a = self.materialization(subject)
        materialization_b = self.materialization(SubjectIdentity(git_tree="tree-2", git_commit="commit", path="."))
        execution_a = self.execution()
        execution_b = self.execution(digest="env-digest-2")
        verification_a = self.verification()
        verification_b = self.verification(revision="dataset-2")

        self.assertEqual(subject.identity(), subject.identity())
        self.assertNotEqual(materialization_a.identity(), materialization_b.identity())
        self.assertNotEqual(execution_a.identity(), execution_b.identity())
        self.assertNotEqual(verification_a.identity(), verification_b.identity())
        self.assertEqual(subject.identity(), self.subject().identity())

    def test_subject_identity_not_conflated_with_other_identity_types(self) -> None:
        subject = self.subject()
        materialization = self.materialization(subject)
        execution = self.execution()
        verification = self.verification()
        self.assertNotEqual(subject.identity(), materialization.identity())
        self.assertNotEqual(subject.identity(), execution.identity())
        self.assertNotEqual(subject.identity(), verification.identity())

    def test_subject_identity_changes_when_logical_subject_changes(self) -> None:
        subject = self.subject()
        mutated_git_tree = SubjectIdentity(git_tree="tree-mutated", git_commit="commit", path=".")
        mutated_git_commit = SubjectIdentity(git_tree="tree", git_commit="commit-mutated", path=".")
        self.assertNotEqual(subject.identity(), mutated_git_tree.identity())
        self.assertNotEqual(subject.identity(), mutated_git_commit.identity())

    def test_provenance_anchor_is_stable_for_identical_inputs(self) -> None:
        a = self.provenance_anchor()
        b = self.provenance_anchor()
        self.assertEqual(a.identity.identity(), b.identity.identity())
        self.assertEqual(
            a.identity.identity(),
            self.provenance_anchor(
                run_id="run-1",
                verifier_id="verifier-1",
                cost_ledger_head="ledger-1",
                cost_ledger_event_count=3,
            ).identity.identity(),
        )

    def test_provenance_anchor_changes_with_subject_execution_verification_and_scope(self) -> None:
        base = self.provenance_anchor()
        self.assertNotEqual(
            base.identity.identity(),
            self.provenance_anchor(subject=SubjectIdentity(git_tree="tree-2", git_commit="commit", path=".")).identity.identity(),
        )
        self.assertNotEqual(
            base.identity.identity(),
            self.provenance_anchor(execution=self.execution(digest="env-digest-2")).identity.identity(),
        )
        self.assertNotEqual(
            base.identity.identity(),
            self.provenance_anchor(verification=self.verification(revision="dataset-2")).identity.identity(),
        )
        self.assertNotEqual(
            base.identity.identity(),
            self.provenance_anchor(scope_policy=self.scope_policy(scope_budget="budget-2")).identity.identity(),
        )

    def test_provenance_anchor_changes_with_producer_and_verifier_context(self) -> None:
        base = self.provenance_anchor()
        self.assertNotEqual(
            base.identity.identity(),
            self.provenance_anchor(run_id="run-2").identity.identity(),
        )
        self.assertNotEqual(
            base.identity.identity(),
            self.provenance_anchor(verifier_id="verifier-2").identity.identity(),
        )

    def test_provenance_anchor_changes_with_ledger_inputs(self) -> None:
        base = self.provenance_anchor()
        self.assertNotEqual(
            base.identity.identity(),
            self.provenance_anchor(cost_ledger_head="ledger-2").identity.identity(),
        )
        self.assertNotEqual(
            base.identity.identity(),
            self.provenance_anchor(cost_ledger_event_count=9).identity.identity(),
        )

    def test_provenance_anchor_changes_with_scope_result(self) -> None:
        base = self.provenance_anchor(scope_decision=ScopeDecision.ALLOW)
        blocked = self.provenance_anchor(scope_decision=ScopeDecision.BLOCK)
        review = self.provenance_anchor(scope_decision=ScopeDecision.REVIEW)
        self.assertNotEqual(base.identity.identity(), blocked.identity.identity())
        self.assertNotEqual(base.identity.identity(), review.identity.identity())
        self.assertNotEqual(blocked.identity.identity(), review.identity.identity())

    def test_provenance_anchor_missing_component_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            build_provenance_anchor(
                ProvenanceAnchorInputs(
                    subject_identity=None,  # type: ignore[arg-type]
                    execution_context_identity=None,  # type: ignore[arg-type]
                    verification_context_identity=None,  # type: ignore[arg-type]
                    scope_policy_identity=None,  # type: ignore[arg-type]
                    run_id="run-1",
                    verifier_id="verifier-1",
                )
            )

    def test_provenance_anchor_is_binding_not_attestation_or_trust(self) -> None:
        anchor = self.provenance_anchor()
        anchor_id = anchor.identity.identity()
        self.assertIsInstance(anchor_id, str)
        self.assertEqual(
            anchor_id,
            self.provenance_anchor(
                subject=self.subject(),
                execution=self.execution(),
                verification=self.verification(),
                scope_policy=self.scope_policy(),
                run_id="run-1",
                verifier_id="verifier-1",
                cost_ledger_head="ledger-1",
                cost_ledger_event_count=3,
            ).identity.identity(),
        )
        self.assertEqual(
            anchor_id,
            self.provenance_anchor(
                subject=self.subject(),
                execution=self.execution(),
                verification=self.verification(),
                scope_policy=self.scope_policy(),
                run_id="run-1",
                verifier_id="verifier-1",
                cost_ledger_head="ledger-1",
                cost_ledger_event_count=3,
            ).identity.identity(),
        )
        self.assertNotIn("sign", type(anchor.identity).__dict__)
        self.assertNotIn("verify_signature", type(anchor.identity).__dict__)
        self.assertNotIn("trust", type(anchor.identity).__dict__)
        self.assertNotIn("attest", type(anchor.identity).__dict__)
        self.assertNotIn("certify", type(anchor.identity).__dict__)
        self.assertNotIn("endorse", type(anchor.identity).__dict__)

    def test_provenance_anchor_does_not_override_acceptance_or_runtime_claims(self) -> None:
        valid_observation = self.observation()
        self.assertEqual(evaluate_acceptance(valid_observation).outcome, AcceptanceOutcome.EVAL_DONE)

        fail_observation = self.observation(verifier_result=ResultStatus.FAIL)
        self.assertEqual(evaluate_acceptance(fail_observation).outcome, AcceptanceOutcome.NOT_ACCEPTED)

        block_observation = self.observation(
            scope_evaluation=self.scope_evaluation(
                operation=ScopeOperation.REPLACE,
                before_path="allowed/config",
                after_path="allowed/config",
                before_object_type=ScopeObjectType.FILE,
                after_object_type=ScopeObjectType.SYMLINK,
            )
        )
        self.assertEqual(evaluate_acceptance(block_observation).outcome, AcceptanceOutcome.NOT_ACCEPTED)
        self.assertEqual(self.provenance_anchor().identity.anchor_type, "oma7:provenance-anchor:v1")

    def test_post_verification_subject_mutation_invalidates_provenance_evidence(self) -> None:
        base = self.provenance_anchor()
        mutated_subject = SubjectIdentity(git_tree="tree-2", git_commit="commit", path=".")
        mutated = build_provenance_anchor(
            self.provenance_inputs(subject=mutated_subject)
        )
        self.assertNotEqual(base.identity.identity(), mutated.identity.identity())

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

    def test_scope_canonicalization_and_containment(self) -> None:
        cases = [
            ("allowed path", "allowed/file.txt", "allowed/file.txt", ScopeDecision.ALLOW),
            ("dot traversal escape", "allowed/../secrets/key.txt", "secrets/key.txt", ScopeDecision.BLOCK),
            ("dot prefixed allowed", "./allowed/file.txt", "allowed/file.txt", ScopeDecision.ALLOW),
            ("nested traversal escape", "allowed/sub/../../secrets/key.txt", "secrets/key.txt", ScopeDecision.BLOCK),
            ("mixed separators", "allowed\\file.txt", "allowed/file.txt", ScopeDecision.ALLOW),
            ("absolute escape", "C:/secrets/key.txt", None, ScopeDecision.BLOCK),
        ]
        for name, path, canonical, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(canonicalize_scope_path(path), canonical)
                decision = evaluate_scope_change(
                    self.scope_change(after_path=path),
                    self.scope_runtime_policy(),
                    subject_identity=self.subject(),
                    materialization_identity=self.materialization(),
                    authorized_primary_change_ids=("primary-1",),
                )
                self.assertEqual(decision.decision, expected)

    def test_scope_transition_semantics_precede_allowlist(self) -> None:
        policy = self.scope_runtime_policy()
        cases = [
            (
                "allowed normal mutation",
                self.scope_change(operation=ScopeOperation.MODIFY, after_path="allowed/config"),
                ScopeDecision.ALLOW,
            ),
            (
                "allowed path dangerous symlink replacement",
                self.scope_change(
                    operation=ScopeOperation.REPLACE,
                    before_path="allowed/config",
                    after_path="allowed/config",
                    before_object_type=ScopeObjectType.FILE,
                    after_object_type=ScopeObjectType.SYMLINK,
                ),
                ScopeDecision.BLOCK,
            ),
            (
                "rename allowed to forbidden",
                self.scope_change(
                    operation=ScopeOperation.RENAME,
                    before_path="allowed/config",
                    after_path="secrets/config",
                ),
                ScopeDecision.BLOCK,
            ),
            (
                "rename forbidden to allowed",
                self.scope_change(
                    operation=ScopeOperation.RENAME,
                    before_path="secrets/config",
                    after_path="allowed/config",
                ),
                ScopeDecision.REVIEW,
            ),
            (
                "object type transition",
                self.scope_change(
                    operation=ScopeOperation.OBJECT_TYPE_CHANGE,
                    before_path="allowed/config",
                    after_path="allowed/config",
                    before_object_type=ScopeObjectType.FILE,
                    after_object_type=ScopeObjectType.DIRECTORY,
                ),
                ScopeDecision.BLOCK,
            ),
            (
                "mode transition",
                self.scope_change(
                    operation=ScopeOperation.MODE_CHANGE,
                    before_path="allowed/config",
                    after_path="allowed/config",
                ),
                ScopeDecision.ALLOW,
            ),
        ]
        for name, change, expected in cases:
            with self.subTest(name=name):
                decision = evaluate_scope_change(
                    change,
                    policy,
                    subject_identity=self.subject(),
                    materialization_identity=self.materialization(),
                    authorized_primary_change_ids=("primary-1",),
                )
                self.assertEqual(decision.decision, expected)

    def test_scope_generated_and_secondary_causality(self) -> None:
        policy = self.scope_runtime_policy()
        cases = [
            (
                "authorized generated change",
                self.scope_change(
                    operation=ScopeOperation.MODIFY,
                    after_path="generated/lockfile.lock",
                    mutation_kind=ScopeMutationKind.GENERATED,
                    parent_change_id="primary-1",
                ),
                ScopeDecision.ALLOW,
            ),
            (
                "unrelated generated mutation",
                self.scope_change(
                    operation=ScopeOperation.MODIFY,
                    after_path="allowed/config",
                    mutation_kind=ScopeMutationKind.GENERATED,
                ),
                ScopeDecision.BLOCK,
            ),
            (
                "secondary collateral mutation",
                self.scope_change(
                    operation=ScopeOperation.MODIFY,
                    after_path="allowed/config",
                    mutation_kind=ScopeMutationKind.SECONDARY,
                ),
                ScopeDecision.BLOCK,
            ),
            (
                "explicitly allowed generated mutation",
                self.scope_change(
                    operation=ScopeOperation.MODIFY,
                    after_path="generated/manifest.json",
                    mutation_kind=ScopeMutationKind.GENERATED,
                    explicitly_allowed=True,
                ),
                ScopeDecision.ALLOW,
            ),
        ]
        for name, change, expected in cases:
            with self.subTest(name=name):
                decision = evaluate_scope_change(
                    change,
                    policy,
                    subject_identity=self.subject(),
                    materialization_identity=self.materialization(),
                    authorized_primary_change_ids=("primary-1",),
                )
                self.assertEqual(decision.decision, expected)

    def test_scope_acceptance_composition_and_staleness(self) -> None:
        pass_scope = self.scope_evaluation()
        review_scope = self.scope_evaluation(
            operation=ScopeOperation.RENAME,
            before_path="secrets/config",
            after_path="allowed/config",
        )
        block_scope = self.scope_evaluation(
            operation=ScopeOperation.REPLACE,
            before_path="allowed/config",
            after_path="allowed/config",
            before_object_type=ScopeObjectType.FILE,
            after_object_type=ScopeObjectType.SYMLINK,
        )
        stale_scope = self.scope_evaluation()
        mutated_subject = SubjectIdentity(git_tree="tree-mutation", git_commit="commit", path=".")

        cases = [
            (
                "functional pass + scope allow",
                self.observation(scope_evaluation=pass_scope),
                AcceptanceOutcome.EVAL_DONE,
                LifecycleState.EVAL_DONE,
            ),
            (
                "functional pass + scope block",
                self.observation(scope_evaluation=block_scope),
                AcceptanceOutcome.NOT_ACCEPTED,
                LifecycleState.VERIFICATION_PENDING,
            ),
            (
                "functional pass + scope review",
                self.observation(scope_evaluation=review_scope),
                AcceptanceOutcome.NOT_ACCEPTED,
                LifecycleState.REVIEW_REQUIRED,
            ),
            (
                "functional fail + scope allow",
                self.observation(scope_evaluation=pass_scope, verifier_result=ResultStatus.FAIL),
                AcceptanceOutcome.NOT_ACCEPTED,
                LifecycleState.VERIFICATION_PENDING,
            ),
            (
                "post-verification mutation invalidates scope evidence",
                self.observation(
                    subject_identity=mutated_subject,
                    materialization_identity=self.materialization(mutated_subject),
                    scope_evaluation=stale_scope,
                ),
                AcceptanceOutcome.NOT_ACCEPTED,
                LifecycleState.VERIFICATION_PENDING,
            ),
        ]
        for name, observation, expected_outcome, expected_state in cases:
            with self.subTest(name=name):
                decision = evaluate_acceptance(observation)
                self.assertEqual(decision.outcome, expected_outcome)
                self.assertEqual(decision.lifecycle_state, expected_state)

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

    def test_execution_context_id_stable_for_same_pins(self) -> None:
        pins_a = self.runtime_pins()
        pins_b = self.runtime_pins()
        self.assertEqual(execution_context_id_from_pins(pins_a), execution_context_id_from_pins(pins_b))

    def test_execution_context_id_changes_for_relevant_pin_change(self) -> None:
        pins_a = self.runtime_pins()
        pins_b = self.runtime_pins(codex_sha256="7ee176b43f96b2294c8e2265d599f829e161b2c2ad34cb2b8fbf5f836fd34b8c")
        self.assertNotEqual(execution_context_id_from_pins(pins_a), execution_context_id_from_pins(pins_b))

    def test_runtime_preflight_passes_with_valid_pins_and_blocked_network(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        original_traversal = preflight._check_traversal_write
        original_symlink = preflight._check_symlink_escape_write
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: True
            preflight._check_traversal_write = lambda workspace: True
            preflight._check_symlink_escape_write = lambda workspace: True
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=True,
                )
            )
            self.assertEqual(result.result, PreflightResult.PASS)
            self.assertTrue(result.pins_valid)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside
            preflight._check_traversal_write = original_traversal
            preflight._check_symlink_escape_write = original_symlink

    def test_preflight_blocks_missing_pin(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: True
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(codex_sha256=""),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=True,
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside

    def test_preflight_blocks_harness_without_commit_or_digest(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: True
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(harness_commit_or_digest="", harness_configuration_digest=""),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=True,
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside

    def test_preflight_blocks_dataset_without_revision(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: True
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(dataset_revision=""),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=True,
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside

    def test_preflight_blocks_mutable_container_tag(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: True
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(container_image_digest="image:tag"),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=True,
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside

    def test_preflight_blocks_interactive_approval(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: True
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(),
                    approval_noninteractive=False,
                    automatic_escalation_disabled=True,
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside

    def test_preflight_blocks_workspace_write_failure(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: False
            preflight._check_outside_workspace_write = lambda workspace: True
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=True,
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside

    def test_preflight_blocks_outside_workspace_write_success(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        original_traversal = preflight._check_traversal_write
        original_symlink = preflight._check_symlink_escape_write
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: False
            preflight._check_traversal_write = lambda workspace: True
            preflight._check_symlink_escape_write = lambda workspace: True
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=True,
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside
            preflight._check_traversal_write = original_traversal
            preflight._check_symlink_escape_write = original_symlink

    def test_preflight_blocks_traversal_write_success(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        original_traversal = preflight._check_traversal_write
        original_symlink = preflight._check_symlink_escape_write
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: True
            preflight._check_traversal_write = lambda workspace: False
            preflight._check_symlink_escape_write = lambda workspace: True
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=True,
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside
            preflight._check_traversal_write = original_traversal
            preflight._check_symlink_escape_write = original_symlink

    def test_preflight_blocks_symlink_escape_write_success(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        original_traversal = preflight._check_traversal_write
        original_symlink = preflight._check_symlink_escape_write
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: True
            preflight._check_traversal_write = lambda workspace: True
            preflight._check_symlink_escape_write = lambda workspace: False
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=True,
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside
            preflight._check_traversal_write = original_traversal
            preflight._check_symlink_escape_write = original_symlink

    def test_preflight_blocks_network_success(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        try:
            preflight._check_network_blocked = lambda: False
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: True
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=True,
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside

    def test_preflight_blocks_automatic_escalation(self) -> None:
        import oma7.preflight as preflight

        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: True
            result = run_sandbox_preflight(
                SandboxPreflightConfig(
                    workspace=self.repo,
                    pins=self.runtime_pins(),
                    approval_noninteractive=True,
                    automatic_escalation_disabled=False,
                )
            )
            self.assertEqual(result.result, PreflightResult.ENVIRONMENT_BLOCKED)
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside

    def test_mission_identity_stability_and_sensitivity(self) -> None:
        subject = self.subject()
        materialization = self.materialization(subject)
        execution = self.execution()
        scope_policy = self.scope_policy()
        mission_a = compute_mission_identity(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            scope_policy_identity=scope_policy,
        )
        mission_b = compute_mission_identity(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            scope_policy_identity=scope_policy,
        )
        mission_c = compute_mission_identity(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=self.execution(digest="env-digest-2"),
            scope_policy_identity=scope_policy,
        )
        self.assertEqual(mission_a.identity(), mission_b.identity())
        self.assertNotEqual(mission_a.identity(), mission_c.identity())

    def test_control_record_round_trip_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            subject = self.subject()
            materialization = self.materialization(subject)
            execution = self.execution()
            scope_policy = self.scope_policy()
            mission = compute_mission_identity(
                subject_identity=subject,
                materialization_identity=materialization,
                execution_context_identity=execution,
                scope_policy_identity=scope_policy,
            )
            policy = control_policy_identity_from_policy(
                max_attempts=2,
                max_elapsed_time_seconds=30,
                max_execution_time_per_attempt_seconds=10,
                retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,),
                non_retryable_classifications=(FailureClassification.NON_RETRYABLE,),
                escalation_reasons=(EscalationReason.AMBIGUOUS_STATE,),
            )
            record = bind_control_record(
                create_control_record(mission_id="m", run_id="r", budget=RetryBudget(2, 30, 10)),
                mission_identity=mission,
                control_policy_identity=policy,
                harness_binding_identity="harness-1:cfg-1",
                subject_identity=subject,
                execution_context_identity=execution,
                scope_policy_identity=scope_policy,
            )
            self.assertTrue(validate_control_record(record))
            write_control_record(path, record)
            loaded = load_control_record(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.mission_identity.identity(), mission.identity())
            self.assertEqual(loaded.control_policy_identity.identity(), policy.identity())
            self.assertEqual(loaded.harness_binding_identity, "harness-1:cfg-1")

    def test_stale_cross_run_rejection(self) -> None:
        import oma7.control_plane as control_plane

        subject = self.subject()
        materialization = self.materialization(subject)
        execution = self.execution()
        scope_policy = self.scope_policy()
        mission = compute_mission_identity(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            scope_policy_identity=scope_policy,
        )
        policy = control_policy_identity_from_policy(
            max_attempts=2,
            max_elapsed_time_seconds=30,
            max_execution_time_per_attempt_seconds=10,
            retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,),
            non_retryable_classifications=(FailureClassification.NON_RETRYABLE,),
            escalation_reasons=(EscalationReason.AMBIGUOUS_STATE,),
        )
        record = bind_control_record(
            create_control_record(mission_id="m", run_id="r1", budget=RetryBudget(2, 30, 10)),
            mission_identity=mission,
            control_policy_identity=policy,
            harness_binding_identity="harness-1:cfg-1",
            subject_identity=subject,
            execution_context_identity=execution,
            scope_policy_identity=scope_policy,
        )
        stale_mission = compute_mission_identity(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=self.execution(digest="env-digest-2"),
            scope_policy_identity=scope_policy,
        )
        self.assertFalse(
            control_plane.preflight_ready(
                record.__class__(**{**record.__dict__, "mission_identity": stale_mission})
            )
        )

    def test_ledger_append_reload_and_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            evidence = self.evidence()
            append_evidence("run-1", evidence, base)
            self.assertEqual(len(load_evidence("run-1", base)), 1)
            ledger = base / "run-1.jsonl"
            ledger.write_text(ledger.read_text(encoding="utf-8") + "{\n", encoding="utf-8")
            self.assertEqual(load_evidence("run-1", base), [])

    def test_preflight_ready_blocked(self) -> None:
        import oma7.preflight as preflight

        subject = self.subject()
        materialization = self.materialization(subject)
        pins = self.runtime_pins()
        execution = ExecutionContextIdentity(
            environment_container_image_digest=pins.container_image_digest,
            codex_binary_digest=pins.codex_sha256,
            codex_version=pins.codex_version,
            model=pins.model,
            reasoning_level=pins.reasoning_level,
            harness_commit_or_digest=pins.harness_commit_or_digest,
            harness_configuration_digest=pins.harness_configuration_digest,
            dependency_lock_digest=pins.dependency_lock_digest,
            dataset_revision=pins.dataset_revision,
            toolchain_identity=pins.toolchain_identity,
        )
        scope_policy = self.scope_policy()
        mission = compute_mission_identity(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            scope_policy_identity=scope_policy,
        )
        policy = control_policy_identity_from_policy(
            max_attempts=2,
            max_elapsed_time_seconds=30,
            max_execution_time_per_attempt_seconds=10,
            retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,),
            non_retryable_classifications=(FailureClassification.NON_RETRYABLE,),
            escalation_reasons=(EscalationReason.AMBIGUOUS_STATE,),
        )
        record = bind_control_record(
            create_control_record(mission_id="m", run_id="r", budget=RetryBudget(2, 30, 10)),
            mission_identity=mission,
            control_policy_identity=policy,
            harness_binding_identity="harness-1:cfg-1",
            subject_identity=subject,
            execution_context_identity=execution,
            scope_policy_identity=scope_policy,
        )
        original_network = preflight._check_network_blocked
        original_workspace = preflight._check_workspace_write
        original_outside = preflight._check_outside_workspace_write
        original_run_sandbox_preflight = preflight.run_sandbox_preflight
        try:
            preflight._check_network_blocked = lambda: True
            preflight._check_workspace_write = lambda workspace: True
            preflight._check_outside_workspace_write = lambda workspace: True
            preflight.run_sandbox_preflight = lambda config: type(
                "SandboxPass",
                (),
                {"result": preflight.PreflightResult.PASS},
            )()
            self.assertEqual(
                preflight.run_production_preflight(
                    preflight.ProductionPreflightConfig(
                        workspace=self.repo,
                        pins=pins,
                        control_record=record,
                    )
                ),
                preflight.ProductionPreflightResult.READY,
            )
            self.assertEqual(
                preflight.run_production_preflight(
                    preflight.ProductionPreflightConfig(
                        workspace=self.repo,
                        pins=self.runtime_pins(codex_sha256="bad"),
                        control_record=record,
                    )
                ),
                preflight.ProductionPreflightResult.BLOCKED,
            )
        finally:
            preflight._check_network_blocked = original_network
            preflight._check_workspace_write = original_workspace
            preflight._check_outside_workspace_write = original_outside
            preflight.run_sandbox_preflight = original_run_sandbox_preflight

    def test_execution_context_identity_from_pins_matches_control_record(self) -> None:
        pins = self.runtime_pins()
        execution = execution_context_identity_from_pins(pins)
        self.assertEqual(execution.identity(), execution_context_id_from_pins(pins))

    def test_dry_run_plan_reuses_canonical_execution_identity_and_blocks_on_mismatch(self) -> None:
        subject = self.subject()
        materialization = self.materialization(subject)
        scope_policy = self.scope_policy()
        pins = self.runtime_pins()
        execution = execution_context_identity_from_pins(pins)
        mission = compute_mission_identity(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            scope_policy_identity=scope_policy,
        )
        policy = control_policy_identity_from_policy(
            max_attempts=2,
            max_elapsed_time_seconds=30,
            max_execution_time_per_attempt_seconds=10,
            retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,),
            non_retryable_classifications=(FailureClassification.NON_RETRYABLE,),
            escalation_reasons=(EscalationReason.AMBIGUOUS_STATE,),
        )
        record = bind_control_record(
            create_control_record(mission_id="m", run_id="r", budget=RetryBudget(2, 30, 10)),
            mission_identity=mission,
            control_policy_identity=policy,
            harness_binding_identity="harness-1:cfg-1",
            subject_identity=subject,
            execution_context_identity=execution,
            scope_policy_identity=scope_policy,
        )
        plan = make_dry_run_plan(ProductionPreflightConfig(workspace=self.repo, pins=pins, control_record=record))
        self.assertEqual(plan.result, ProductionPreflightResult.READY)
        self.assertEqual(plan.execution_context_identity, execution)
        self.assertEqual(plan.execution_context_id, execution.identity())
        blocked = make_dry_run_plan(ProductionPreflightConfig(workspace=self.repo, pins=self.runtime_pins(codex_sha256="bad"), control_record=record))
        self.assertEqual(blocked.result, ProductionPreflightResult.BLOCKED)
        self.assertIsNone(blocked.execution_context_id)

    def test_run_production_preflight_requires_typed_identity_match(self) -> None:
        subject = self.subject()
        materialization = self.materialization(subject)
        scope_policy = self.scope_policy()
        pins = self.runtime_pins()
        execution = execution_context_identity_from_pins(pins)
        mission = compute_mission_identity(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            scope_policy_identity=scope_policy,
        )
        policy = control_policy_identity_from_policy(
            max_attempts=2,
            max_elapsed_time_seconds=30,
            max_execution_time_per_attempt_seconds=10,
            retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,),
            non_retryable_classifications=(FailureClassification.NON_RETRYABLE,),
            escalation_reasons=(EscalationReason.AMBIGUOUS_STATE,),
        )
        record = bind_control_record(
            create_control_record(mission_id="m", run_id="r", budget=RetryBudget(2, 30, 10)),
            mission_identity=mission,
            control_policy_identity=policy,
            harness_binding_identity="harness-1:cfg-1",
            subject_identity=subject,
            execution_context_identity=execution,
            scope_policy_identity=scope_policy,
        )
        self.assertEqual(
            run_production_preflight(ProductionPreflightConfig(workspace=self.repo, pins=pins, control_record=record)),
            ProductionPreflightResult.READY,
        )
        self.assertEqual(
            run_production_preflight(ProductionPreflightConfig(workspace=self.repo, pins=self.runtime_pins(codex_sha256="bad"), control_record=record)),
            ProductionPreflightResult.BLOCKED,
        )

    def test_auth_blocked_zero_attempt_behavior(self) -> None:
        record = create_control_record(mission_id="m", run_id="r", budget=RetryBudget(2, 30, 10))
        self.assertEqual(record.budget_state.attempts_used, 0)
        self.assertFalse(
            can_start_attempt(
                record,
                next_attempt=new_attempt_identity("r", 1, subject_identity=self.subject()),
                retry_reason=FailureClassification.NON_RETRYABLE,
                has_changed_conditions=False,
            )
        )
        self.assertEqual(record.budget_state.attempts_used, 0)




if __name__ == "__main__":
    unittest.main()
