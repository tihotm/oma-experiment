from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oma7.accounting import (
    AccountingEventKind,
    append_cost_entry,
    append_human_intervention,
    cost_ledger_event_count,
    cost_ledger_head,
    human_intervention_summary,
)
from oma7.control_plane import (
    control_policy_identity_from_policy,
    create_control_record as make_control_record,
    RetryBudget,
    SupervisorState,
    classify_restart,
    create_control_record,
    new_attempt_identity,
    record_attempt,
    write_control_record,
)
from oma7.evidence_ledger import append_evidence, append_post_execution_record, load_evidence, load_post_execution_records
from oma7.lifecycle import DurableRunRecord, LifecycleState, RunIdentity, write_durable_run_record, load_durable_run_record
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
from oma7.post_execution import build_a1_record, build_g0_record, build_qualified_pair_record
from oma7.post_execution import A1Record, A1Result
from oma7.recovery import RecoveryDisposition, classify_recovery
from oma7.scope import ProvenanceAnchorInputs, ScopeDecision, build_provenance_anchor


class RecoveryConcurrencyTests(unittest.TestCase):
    def _subject(self) -> SubjectIdentity:
        return SubjectIdentity(git_tree="tree", git_commit="commit", path=".")

    def _materialization(self, subject: SubjectIdentity) -> MaterializationIdentity:
        return MaterializationIdentity(subject_identity=subject, canonical_root_descriptor="root")

    def _execution(self) -> ExecutionContextIdentity:
        return ExecutionContextIdentity(
            environment_container_image_digest="img",
            codex_binary_digest="bin",
            codex_version="1",
            model="m",
            reasoning_level="high",
            harness_commit_or_digest="h",
            harness_configuration_digest="c",
            dependency_lock_digest="d",
            dataset_revision="r",
            toolchain_identity="t",
        )

    def _verification(self) -> VerificationContextIdentity:
        return VerificationContextIdentity(
            dataset_revision="r",
            oracle_test_patch_identity="oracle",
            fail_to_pass=(),
            pass_to_pass=(),
            harness_commit_or_digest="h",
            verification_configuration_digest="vcfg",
            verifier_environment_image_digest="img",
            verifier_identity="verifier-1",
        )

    def _scope(self) -> ScopePolicyIdentity:
        return ScopePolicyIdentity(
            allowed_scope_path_policy=("src/**",),
            protected_semantic_roles=("oracle",),
            explicit_sensitive_change_authorizations=(),
            scope_budget="budget",
            task_specific_exceptions=(),
            rule_schema_version="scope/v1",
        )

    def _evidence(self, run_id: str = "run-1") -> Evidence:
        subject = self._subject()
        materialization = self._materialization(subject)
        execution = self._execution()
        verification = self._verification()
        scope = self._scope()
        provenance = build_provenance_anchor(
            ProvenanceAnchorInputs(
                subject_identity=subject,
                execution_context_identity=execution,
                verification_context_identity=verification,
                scope_policy_identity=scope,
                run_id=run_id,
                verifier_id=verification.verifier_identity,
                cost_ledger_head="ledger-head",
                cost_ledger_event_count=1,
                scope_decision=ScopeDecision.ALLOW,
                scope_change_id="change-1",
            )
        ).identity
        return Evidence(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope,
            provenance_anchor_identity=provenance,
            result=ResultStatus.PASS,
            verifier_id=verification.verifier_identity,
            run_id=run_id,
            cost_ledger_head="ledger-head",
            cost_ledger_event_count=1,
            human_intervention_summary="approved=0;blocked=0;total=0",
        )

    def test_accounting_append_is_idempotent_and_cas_protected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            first = append_cost_entry("run-1", cost_units=5, base_dir=base, expected_next_event_index=1)
            duplicate = append_cost_entry("run-1", cost_units=5, base_dir=base, expected_next_event_index=1)
            self.assertEqual(first.identity(), duplicate.identity())
            self.assertEqual(cost_ledger_event_count("run-1", base), 1)
            self.assertEqual(cost_ledger_head("run-1", base) is not None, True)
            with self.assertRaises(ValueError):
                append_cost_entry("run-1", cost_units=7, base_dir=base, expected_next_event_index=1)
            human = append_human_intervention("run-1", human_actor="operator", reason="override", approved=True, base_dir=base, expected_next_event_index=1)
            human_dup = append_human_intervention("run-1", human_actor="operator", reason="override", approved=True, base_dir=base, expected_next_event_index=1)
            self.assertEqual(human.identity(), human_dup.identity())
            self.assertEqual(human_intervention_summary("run-1", base), "approved=1;blocked=0;total=1")

    def test_evidence_append_is_idempotent_and_stale_writers_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            evidence = self._evidence()
            append_evidence("run-1", evidence, base, expected_next_event_index=1)
            append_evidence("run-1", evidence, base, expected_next_event_index=1)
            self.assertEqual(len(load_evidence("run-1", base)), 1)
            with self.assertRaises(ValueError):
                append_evidence(
                    "run-1",
                    Evidence(
                        subject_identity=evidence.subject_identity,
                        materialization_identity=evidence.materialization_identity,
                        execution_context_identity=evidence.execution_context_identity,
                        verification_context_identity=evidence.verification_context_identity,
                        scope_policy_identity=evidence.scope_policy_identity,
                        provenance_anchor_identity=evidence.provenance_anchor_identity,
                        result=ResultStatus.FAIL,
                        verifier_id=evidence.verifier_id,
                        run_id=evidence.run_id,
                    ),
                    base,
                    expected_next_event_index=1,
                )

    def test_post_execution_append_is_ordered_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            subject = self._subject()
            materialization = self._materialization(subject)
            execution = self._execution()
            evidence = self._evidence()
            mission = __import__("oma7.models", fromlist=["MissionIdentity"]).MissionIdentity(
                subject_identity=subject,
                materialization_identity=materialization,
                execution_context_identity=execution,
                scope_policy_identity=self._scope(),
            )
            attempt = new_attempt_identity("run-1", 1, subject_identity=subject, execution_context_identity=execution)
            g0 = build_g0_record(mission_identity=mission, attempt_identity=attempt, execution_context_identity=execution, evidence=evidence)
            a1 = build_a1_record(g0)
            pair = build_qualified_pair_record(g0, a1)
            append_post_execution_record("run-1", g0, base, expected_next_event_index=1)
            append_post_execution_record("run-1", g0, base, expected_next_event_index=1)
            append_post_execution_record("run-1", a1, base, expected_next_event_index=2)
            append_post_execution_record("run-1", pair, base, expected_next_event_index=3)
            self.assertEqual(len(load_post_execution_records("run-1", base)), 3)
            with self.assertRaises(ValueError):
                append_post_execution_record(
                    "run-1",
                    A1Record(
                        schema_version="oma7.post-execution/v1",
                        g0_record=g0,
                        result=A1Result(state=g0.result.state, reason="stale writer"),
                    ),
                    base,
                    expected_next_event_index=2,
                )

    def test_recovery_classification_uses_persisted_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            subject = self._subject()
            materialization = self._materialization(subject)
            execution = self._execution()
            verification = self._verification()
            scope = self._scope()
            provenance = build_provenance_anchor(
                ProvenanceAnchorInputs(
                    subject_identity=subject,
                    execution_context_identity=execution,
                    verification_context_identity=verification,
                    scope_policy_identity=scope,
                    run_id="run-1",
                    verifier_id=verification.verifier_identity,
                    cost_ledger_head="ledger-head",
                    cost_ledger_event_count=1,
                    scope_decision=ScopeDecision.ALLOW,
                    scope_change_id="change-1",
                )
            ).identity
            run_identity = RunIdentity("inst", "phase", "rep", subject, materialization, execution, verification, scope, provenance)
            write_durable_run_record(
                base / "run.json",
                DurableRunRecord(
                    schema_version="oma7.run-record/v1",
                    run_identity=run_identity,
                    lifecycle_state=LifecycleState.EVAL_DONE,
                    evidence_reference=str(base / "evidence.json"),
                    evidence_identity=self._evidence().identity(),
                    durability={"file_fsync_performed": True, "directory_fsync_performed": True, "atomic_replace_used": True},
                ),
            )
            mission = __import__("oma7.models", fromlist=["compute_mission_identity"]).compute_mission_identity(
                subject_identity=subject,
                materialization_identity=materialization,
                execution_context_identity=execution,
                scope_policy_identity=scope,
            )
            control_policy = control_policy_identity_from_policy(
                max_attempts=2,
                max_elapsed_time_seconds=30,
                max_execution_time_per_attempt_seconds=10,
                retryable_classifications=(),
                non_retryable_classifications=(),
                escalation_reasons=(),
            )
            write_control_record(
                base / "control.json",
                make_control_record(
                    run_id="run-1",
                    budget=RetryBudget(2, 30, 10),
                    mission_identity=mission,
                    control_policy_identity=control_policy,
                    harness_binding_identity="harness-1:cfg-1",
                    subject_identity=subject,
                    execution_context_identity=execution,
                    scope_policy_identity=scope,
                ).with_attempt(record_attempt(new_attempt_identity("run-1", 1, subject_identity=subject), SupervisorState.VERIFYING)),
            )
            decision = classify_recovery(
                control_record_path=base / "control.json",
                run_record_path=base / "run.json",
                evidence_path=base / "evidence.json",
                accounting_run_id="run-1",
                post_execution_run_id="run-1",
                expected_run_identity=run_identity,
            )
            self.assertIn(decision.disposition, {RecoveryDisposition.CONTINUE, RecoveryDisposition.RETRY, RecoveryDisposition.NO_OP})


if __name__ == "__main__":
    unittest.main()
