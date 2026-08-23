from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oma7 import (
    A1Record,
    G0Record,
    QualifiedPairRecord,
    build_a1_record,
    build_g0_record,
    build_qualified_pair_record,
    provenance_chain_reconstructible,
)
from oma7.control_plane import (
    AttemptIdentity,
    FailureClassification,
    SupervisorState,
    duplicate_acceptance_prevented,
    duplicate_execution_prevented,
    new_attempt_identity,
)
from oma7.evidence_ledger import append_post_execution_record, load_post_execution_records
from oma7.lifecycle import (
    ControlledLifecycleObservation,
    DurableRunRecord,
    LifecycleState,
    ResumeClassification,
    RunIdentity,
    classify_resume_state,
    load_durable_run_record,
    load_published_evidence,
    publish_atomic_evidence,
    write_durable_run_record,
)
from oma7.models import (
    ExecutionContextIdentity,
    Evidence,
    MaterializationIdentity,
    MissionIdentity,
    QualificationState,
    ResultStatus,
    ScopePolicyIdentity,
    SubjectIdentity,
)
from oma7.preflight import RuntimePins, execution_context_identity_from_pins


class PostExecutionPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.subject = SubjectIdentity(git_tree="tree-1", git_commit="commit-1", path=".")
        self.materialization = MaterializationIdentity(
            subject_identity=self.subject,
            canonical_root_descriptor="root",
            symlink_topology=(),
            hardlink_topology=(),
            worktree_reference_identity="worktree-1",
            mounted_reference_artifact_identities=(),
            cache_manifest_digest="cache-1",
        )
        self.scope = ScopePolicyIdentity(
            allowed_scope_path_policy=("src/**",),
            protected_semantic_roles=("core",),
            explicit_sensitive_change_authorizations=(),
            scope_budget="bounded",
            task_specific_exceptions=(),
            rule_schema_version="oma7.scope-policy/v1",
        )
        self.pins = RuntimePins(
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
        self.execution = execution_context_identity_from_pins(self.pins)
        self.mission = MissionIdentity(
            subject_identity=self.subject,
            materialization_identity=self.materialization,
            execution_context_identity=self.execution,
            scope_policy_identity=self.scope,
        )
        self.attempt = new_attempt_identity("run-1", 1, subject_identity=self.subject, execution_context_identity=self.execution)
        self.evidence = Evidence(
            subject_identity=self.subject,
            materialization_identity=self.materialization,
            execution_context_identity=self.execution,
            verification_context_identity=None,
            scope_policy_identity=self.scope,
            provenance_anchor_identity=None,
            result=ResultStatus.PASS,
            run_id="run-1",
            predicate={"kind": "real-execution"},
        )

    def test_g0_rejects_incompatible_execution_context(self) -> None:
        g0 = build_g0_record(
            mission_identity=self.mission,
            attempt_identity=self.attempt,
            execution_context_identity=ExecutionContextIdentity(
                environment_container_image_digest="sha256:" + "0" * 64,
                codex_binary_digest=self.pins.codex_sha256,
                codex_version=self.pins.codex_version,
                model=self.pins.model,
                reasoning_level=self.pins.reasoning_level,
                harness_commit_or_digest=self.pins.harness_commit_or_digest,
                harness_configuration_digest=self.pins.harness_configuration_digest,
                dependency_lock_digest=self.pins.dependency_lock_digest,
                dataset_revision=self.pins.dataset_revision,
                toolchain_identity=self.pins.toolchain_identity,
            ),
            evidence=self.evidence,
        )
        self.assertFalse(g0.is_eligible())
        self.assertEqual(g0.result.state, QualificationState.EXECUTION_FAILED)

    def test_g0_a1_and_pair_require_consistent_real_like_fixture(self) -> None:
        g0 = build_g0_record(
            mission_identity=self.mission,
            attempt_identity=self.attempt,
            execution_context_identity=self.execution,
            evidence=self.evidence,
        )
        self.assertTrue(g0.is_eligible())
        a1 = build_a1_record(g0)
        self.assertTrue(a1.is_eligible())
        pair = build_qualified_pair_record(g0, a1)
        self.assertTrue(pair.is_eligible())
        self.assertTrue(provenance_chain_reconstructible(g0, a1, pair))

    def test_pair_rejects_mismatched_attempt(self) -> None:
        g0 = build_g0_record(
            mission_identity=self.mission,
            attempt_identity=self.attempt,
            execution_context_identity=self.execution,
            evidence=self.evidence,
        )
        other_attempt = new_attempt_identity("run-1", 2, subject_identity=self.subject, execution_context_identity=self.execution)
        other_g0 = G0Record(
            schema_version=g0.schema_version,
            mission_identity=g0.mission_identity,
            attempt_identity=other_attempt,
            execution_context_identity=g0.execution_context_identity,
            evidence=g0.evidence,
            result=g0.result,
        )
        pair = build_qualified_pair_record(g0, build_a1_record(other_g0))
        self.assertFalse(pair.is_eligible())

    def test_ledger_reconstructs_post_execution_chain(self) -> None:
        g0 = build_g0_record(
            mission_identity=self.mission,
            attempt_identity=self.attempt,
            execution_context_identity=self.execution,
            evidence=self.evidence,
        )
        a1 = build_a1_record(g0)
        pair = build_qualified_pair_record(g0, a1)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            append_post_execution_record("run-1", g0, base)
            append_post_execution_record("run-1", a1, base)
            append_post_execution_record("run-1", pair, base)
            records = load_post_execution_records("run-1", base)
            self.assertEqual(len(records), 3)
            self.assertEqual(records[0]["record"]["schema_version"], "oma7.post-execution/v1")

    def test_resume_and_idempotency_boundaries_are_deterministic(self) -> None:
        self.assertTrue(duplicate_execution_prevented((), "run-1"))
        self.assertTrue(duplicate_acceptance_prevented(None, None))
        self.assertTrue(
            duplicate_execution_prevented(
                (
                    SimpleNamespace(
                        attempt_identity=SimpleNamespace(run_id="run-1"),
                        state=SupervisorState.RUNNING,
                    ),
                ),
                "run-1",
            )
        )
        self.assertTrue(
            duplicate_execution_prevented(
                (
                    __import__("types").SimpleNamespace(
                        attempt_identity=self.attempt,
                        state=SupervisorState.RUNNING,
                    ),
                ),
                "run-1",
            )
        )

    def test_durable_resume_and_finalize_conflicts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_identity = RunIdentity(
                instance_id="instance-1",
                phase="g0",
                replicate="replica-1",
                subject_identity=self.subject,
                materialization_identity=self.materialization,
                execution_context_identity=self.execution,
                verification_context_identity=None,
                scope_policy_identity=self.scope,
                provenance_anchor_identity=None,
            )
            run_record = DurableRunRecord(
                schema_version="oma7.run-record/v1",
                run_identity=run_identity,
                lifecycle_state=LifecycleState.EVAL_DONE,
                evidence_reference=str(base / "evidence.json"),
                evidence_identity="evidence-1",
                durability={"file_fsync_performed": True, "directory_fsync_performed": True, "atomic_replace_used": True},
            )
            write_durable_run_record(base / "run.json", run_record)
            self.assertEqual(
                classify_resume_state(load_durable_run_record(base / "run.json"), None, run_identity),
                ResumeClassification.INVALID,
            )

    def test_atomic_evidence_publication_remains_ledger_reconstructible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            publish_atomic_evidence(base / "evidence.json", self.evidence)
            self.assertIsNotNone(load_published_evidence(base / "evidence.json"))


if __name__ == "__main__":
    unittest.main()
