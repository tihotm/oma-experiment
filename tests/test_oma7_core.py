from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.git_identity import compute_git_tree_identity
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


if __name__ == "__main__":
    unittest.main()
