from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.control_plane import (
    RetryBudget,
    SupervisorState,
    classify_failure,
    classify_restart,
    can_retry,
    can_start_attempt,
    create_control_record,
    duplicate_acceptance_prevented,
    duplicate_execution_prevented,
    load_control_record,
    new_attempt_identity,
    record_attempt,
    update_budget_state,
    validate_control_record,
    write_control_record,
)
from oma7.lifecycle import (
    AcceptanceOutcome,
    ControlledLifecycleObservation,
    GateStatus,
    LifecycleState,
    ResumeClassification,
    DurableRunRecord,
    RunIdentity,
    evidence_publication_payload,
    finalize_durable_done,
    load_durable_run_record,
    load_published_evidence,
    publish_atomic_evidence,
    classify_resume_state,
    SUPPORTED_RUN_RECORD_SCHEMA,
    evaluate_acceptance,
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
from oma7.scope import ScopeDecision, ScopeEvaluation, ScopePolicy, evaluate_scope_change, ScopeChange, ScopeOperation, ScopeObjectType, ProvenanceAnchorInputs, build_provenance_anchor


def _subject(tag: str = "a") -> SubjectIdentity:
    return SubjectIdentity(git_tree=f"tree-{tag}", git_commit=f"commit-{tag}", path=".")


def _materialization(subject: SubjectIdentity) -> MaterializationIdentity:
    return MaterializationIdentity(subject_identity=subject, canonical_root_descriptor="root")


def _execution(tag: str = "exec") -> ExecutionContextIdentity:
    return ExecutionContextIdentity(
        environment_container_image_digest=f"img-{tag}",
        codex_binary_digest="codex",
        codex_version="1",
        model="m",
        reasoning_level="high",
        harness_commit_or_digest="h",
        harness_configuration_digest="c",
        dependency_lock_digest="d",
        dataset_revision="r",
        toolchain_identity="t",
    )


def _verification(tag: str = "ver") -> VerificationContextIdentity:
    return VerificationContextIdentity(
        dataset_revision="r",
        oracle_test_patch_identity=f"oracle-{tag}",
        fail_to_pass=(),
        pass_to_pass=(),
        harness_commit_or_digest="h",
        verification_configuration_digest="vcfg",
        verifier_environment_image_digest=f"img-{tag}",
        verifier_identity=f"verifier-{tag}",
    )


def _scope_identity(tag: str = "s") -> ScopePolicyIdentity:
    return ScopePolicyIdentity(
        allowed_scope_path_policy=("src/**",),
        protected_semantic_roles=("oracle",),
        explicit_sensitive_change_authorizations=(),
        scope_budget=f"budget-{tag}",
        task_specific_exceptions=(),
        rule_schema_version="scope/v1",
    )


def _provenance(subject: SubjectIdentity, verification: VerificationContextIdentity, scope_identity: ScopePolicyIdentity, run_id: str, verifier_id: str) -> ProvenanceAnchorIdentity:
    return build_provenance_anchor(
        ProvenanceAnchorInputs(
            subject_identity=subject,
            execution_context_identity=_execution(),
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            run_id=run_id,
            verifier_id=verifier_id,
            cost_ledger_head="ledger",
            cost_ledger_event_count=1,
            scope_decision=ScopeDecision.ALLOW,
            scope_change_id="change-1",
        )
    ).identity


def _scope_eval(subject: SubjectIdentity, materialization: MaterializationIdentity, decision: ScopeDecision = ScopeDecision.ALLOW) -> ScopeEvaluation:
    return evaluate_scope_change(
        ScopeChange(
            operation=ScopeOperation.MODIFY,
            before_path="src/file.txt",
            after_path="src/file.txt",
            before_object_type=ScopeObjectType.FILE,
            after_object_type=ScopeObjectType.FILE,
            before_identity="before",
            after_identity="after",
        ),
        ScopePolicy(("src/**", "tests/**")),
        subject_identity=subject,
        materialization_identity=materialization,
    )


def _evidence(subject: SubjectIdentity, materialization: MaterializationIdentity, execution: ExecutionContextIdentity, verification: VerificationContextIdentity, scope_identity: ScopePolicyIdentity, provenance: ProvenanceAnchorIdentity, run_id: str = "run-1") -> Evidence:
    return Evidence(
        subject_identity=subject,
        materialization_identity=materialization,
        execution_context_identity=execution,
        verification_context_identity=verification,
        scope_policy_identity=scope_identity,
        provenance_anchor_identity=provenance,
        result=ResultStatus.PASS,
        verifier_id=verification.verifier_identity,
        run_id=run_id,
    )


class ControlPlaneOfflineTests(unittest.TestCase):
    def test_corrupt_state_cases_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            cases = [
                "",
                "{",
                '{"schema_version":"x"}',
                '{"schema_version":"oma7.supervisor-control/v1","mission_id":"","run_id":"r","state":"PENDING","budget":{"max_attempts":1,"max_elapsed_time_seconds":1,"max_execution_time_per_attempt_seconds":1},"budget_state":{"attempts_used":0,"elapsed_seconds":0,"cost_used":0}}',
                '{"schema_version":"oma7.supervisor-control/v1","mission_id":"m","run_id":"r","state":"RUNNING","budget":{"max_attempts":1,"max_elapsed_time_seconds":1,"max_execution_time_per_attempt_seconds":1},"budget_state":{"attempts_used":0,"elapsed_seconds":0,"cost_used":0}}',
                '{"schema_version":"oma7.supervisor-control/v1","mission_id":"m","run_id":"r","state":"ACCEPTED","budget":{"max_attempts":1,"max_elapsed_time_seconds":1,"max_execution_time_per_attempt_seconds":1},"budget_state":{"attempts_used":0,"elapsed_seconds":0,"cost_used":0},"failure_classification":"NON_RETRYABLE"}',
            ]
            for payload in cases:
                path.write_text(payload, encoding="utf-8")
                self.assertIsNone(load_control_record(path))

            record = create_control_record(mission_id="m", run_id="r", budget=RetryBudget(1, 1, 1))
            self.assertTrue(validate_control_record(record))
            bad = replace(record, current_attempt_id="missing")
            self.assertFalse(validate_control_record(bad))

            record = replace(record, attempts=(record_attempt(new_attempt_identity("r", 1), SupervisorState.RUNNING), record_attempt(new_attempt_identity("r", 1), SupervisorState.RETRYABLE_FAILURE)))
            self.assertFalse(validate_control_record(record))

    def test_resume_after_freeze_and_verification_reuse(self) -> None:
        subject = _subject()
        materialization = _materialization(subject)
        execution = _execution()
        verification = _verification()
        scope_identity = _scope_identity()
        provenance = _provenance(subject, verification, scope_identity, "run-1", "verifier-1")
        evidence = _evidence(subject, materialization, execution, verification, scope_identity, provenance)
        scope_eval = _scope_eval(subject, materialization)
        observation = ControlledLifecycleObservation(
            executor_state=LifecycleState.FROZEN,
            lifecycle_state=LifecycleState.VERIFICATION_PENDING,
            verifier_result=ResultStatus.PASS,
            evidence=evidence,
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance,
            scope_evaluation=scope_eval,
            quiescence_status=GateStatus.PASS_,
            freeze_status=GateStatus.PASS_,
            integrity_status=GateStatus.PASS_,
        )
        self.assertEqual(evaluate_acceptance(observation).outcome, AcceptanceOutcome.EVAL_DONE)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_record = root / "run.json"
            evidence_path = root / "evidence.json"
            expected = RunIdentity("inst", "phase", "rep", subject, materialization, execution, verification, scope_identity, provenance)
            write_result = finalize_durable_done(run_record, evidence_path, expected, observation)
            self.assertEqual(write_result, ResumeClassification.INVALID)
            publish_atomic_evidence(evidence_path, evidence_publication_payload(evidence))
            attempt = new_attempt_identity("run-1", 1, subject_identity=subject)
            write_control = create_control_record(mission_id="m", run_id="run-1", budget=RetryBudget(2, 30, 10))
            write_control = write_control.with_attempt(record_attempt(attempt, SupervisorState.VERIFYING, evidence_reference=str(evidence_path)))
            write_control = replace(write_control, state=SupervisorState.VERIFYING)
            write_control_record(root / "control.json", write_control)
            loaded = load_control_record(root / "control.json")
            self.assertEqual(classify_restart(loaded, frozen_submission_exists=True, verifier_complete=False), SupervisorState.VERIFYING)
            self.assertEqual(classify_restart(loaded, frozen_submission_exists=True, verifier_complete=True), SupervisorState.VERIFYING)

    def test_retry_and_duplicate_policy_matrix(self) -> None:
        budget = RetryBudget(2, 10, 5)
        state = create_control_record(mission_id="m", run_id="r", budget=budget)
        attempts = []
        for idx in range(3):
            attempt = new_attempt_identity("r", idx + 1, subject_identity=_subject(str(idx)))
            attempts.append(record_attempt(attempt, SupervisorState.RUNNING if idx == 0 else SupervisorState.RETRYABLE_FAILURE))
        self.assertTrue(duplicate_execution_prevented((attempts[0],), "r"))
        self.assertTrue(can_start_attempt(state, next_attempt=attempts[0].attempt_identity, has_changed_conditions=True))
        self.assertFalse(can_start_attempt(replace(state, state=SupervisorState.ACCEPTED), next_attempt=attempts[0].attempt_identity, has_changed_conditions=False))
        self.assertFalse(can_retry(classify_failure(auth_missing=True), budget, state.budget_state, progress_exists=False, context_changed=False, attempt_number=1))
        self.assertTrue(can_retry(classify_failure(infrastructure_failure=True), budget, state.budget_state, progress_exists=True, context_changed=False, attempt_number=1))

    def test_auth_required_and_cross_run_isolation(self) -> None:
        record = create_control_record(mission_id="m", run_id="A", budget=RetryBudget(2, 10, 5))
        self.assertEqual(classify_restart(record), SupervisorState.PENDING)
        self.assertFalse(validate_control_record(replace(record, run_id="B", current_attempt_id="A:1", state=SupervisorState.RUNNING)))
        subject = _subject("a")
        materialization = _materialization(subject)
        execution = _execution("a")
        verification = _verification("a")
        scope_identity = _scope_identity("a")
        provenance = _provenance(subject, verification, scope_identity, "A", "v")
        evidence = _evidence(subject, materialization, execution, verification, scope_identity, provenance, run_id="A")
        self.assertTrue(duplicate_acceptance_prevented(evidence, evidence))
        self.assertFalse(duplicate_acceptance_prevented(evidence, _evidence(_subject("b"), _materialization(_subject("b")), _execution("b"), _verification("b"), _scope_identity("b"), _provenance(_subject("b"), _verification("b"), _scope_identity("b"), "B", "v"), run_id="B")))

    def test_state_sequence_properties(self) -> None:
        seed = 42
        state = create_control_record(mission_id="m", run_id="r", budget=RetryBudget(3, 50, 10))
        seen = []
        for i in range(500):
            if i % 7 == 0:
                state = replace(state, budget_state=update_budget_state(state.budget_state, attempts_delta=1))
            elif i % 7 == 1:
                state = replace(state, state=SupervisorState.RUNNING, current_attempt_id=f"r:{(i // 7) + 1}")
            elif i % 7 == 2:
                state = replace(state, state=SupervisorState.VERIFYING)
            elif i % 7 == 3:
                state = replace(state, state=SupervisorState.RETRYABLE_FAILURE)
            elif i % 7 == 4:
                state = replace(state, state=SupervisorState.ACCEPTED)
            elif i % 7 == 5:
                state = replace(state, budget_state=update_budget_state(state.budget_state, elapsed_delta=0.1))
            else:
                state = replace(state, latest_transition=f"s{i}")
            self.assertGreaterEqual(state.budget_state.attempts_used, 0)
            self.assertGreaterEqual(state.budget_state.elapsed_seconds, 0)
            seen.append(state.state)
        self.assertEqual(len(seen), 500)

    def test_control_policy_identity_canonical(self) -> None:
        from oma7.control_plane import control_policy_identity_from_policy, FailureClassification, EscalationReason
        a = control_policy_identity_from_policy(max_attempts=2, max_elapsed_time_seconds=10, max_execution_time_per_attempt_seconds=5, retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,), non_retryable_classifications=(FailureClassification.NON_RETRYABLE,), escalation_reasons=(EscalationReason.AMBIGUOUS_STATE,), pointless_identical_retry_blocked=True)
        b = control_policy_identity_from_policy(max_attempts=2, max_elapsed_time_seconds=10, max_execution_time_per_attempt_seconds=5, retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,), non_retryable_classifications=(FailureClassification.NON_RETRYABLE,), escalation_reasons=(EscalationReason.AMBIGUOUS_STATE,), pointless_identical_retry_blocked=True)
        c = control_policy_identity_from_policy(max_attempts=3, max_elapsed_time_seconds=10, max_execution_time_per_attempt_seconds=5, retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,), non_retryable_classifications=(FailureClassification.NON_RETRYABLE,), escalation_reasons=(EscalationReason.AMBIGUOUS_STATE,), pointless_identical_retry_blocked=True)
        self.assertEqual(a.identity(), b.identity())
        self.assertNotEqual(a.identity(), c.identity())


if __name__ == "__main__":
    unittest.main()
