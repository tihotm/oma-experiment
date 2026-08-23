from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.control_plane import (
    AttemptRecord,
    AttemptIdentity,
    BudgetState,
    ControlPolicyIdentity,
    EscalationReason,
    FailureClassification,
    RetryBudget,
    SupervisorControlRecord,
    SupervisorState,
    control_policy_identity_from_policy,
    can_start_attempt,
    can_retry,
    classify_failure,
    classify_restart,
    create_control_record as _create_control_record,
    duplicate_acceptance_prevented,
    duplicate_execution_prevented,
    escalation_justified,
    load_control_record,
    new_attempt_identity,
    progress_is_reusable,
    record_attempt,
    validate_control_record,
    stale_progress_reuse_rejected,
    transition_allowed,
    update_budget_state,
    write_control_record,
)
from oma7.lifecycle import evaluate_acceptance
from oma7.docker_lifecycle import build_synthetic_acceptance_observation, docker_executable
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
from oma7.scope import (
    ProvenanceAnchorInputs,
    ScopeChange,
    ScopeDecision,
    ScopeOperation,
    ScopePolicy,
    ScopeObjectType,
    build_provenance_anchor,
    evaluate_scope_change,
)



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


def _docker_available() -> bool:
    try:
        return bool(docker_executable())
    except Exception:
        return False


class SupervisionTests(unittest.TestCase):
    def subject(self) -> SubjectIdentity:
        return SubjectIdentity(git_tree="tree", git_commit="commit", path=".")

    def materialization(self, subject: SubjectIdentity | None = None) -> MaterializationIdentity:
        subject = subject or self.subject()
        return MaterializationIdentity(subject_identity=subject, canonical_root_descriptor="git:root")

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

    def scope_policy(self) -> ScopePolicyIdentity:
        return ScopePolicyIdentity(
            allowed_scope_path_policy=("src/**",),
            protected_semantic_roles=("oracle",),
            explicit_sensitive_change_authorizations=(),
            scope_budget="scope-budget-1",
            task_specific_exceptions=(),
            rule_schema_version="scope/v1",
        )

    def scope_runtime_policy(self) -> ScopePolicy:
        return ScopePolicy(("src/**", "tests/**"))

    def scope_change(self) -> ScopeChange:
        return ScopeChange(
            operation=ScopeOperation.MODIFY,
            before_path="src/oma7/control_plane.py",
            after_path="src/oma7/control_plane.py",
            before_object_type=ScopeObjectType.FILE,
            after_object_type=ScopeObjectType.FILE,
            before_identity="before",
            after_identity="after",
        )

    def evidence(self) -> Evidence:
        subject = self.subject()
        materialization = self.materialization(subject)
        execution = ExecutionContextIdentity(
            environment_container_image_digest="img",
            codex_binary_digest="bin",
            codex_version="0",
            model="synthetic",
            reasoning_level="high",
            harness_commit_or_digest="h",
            harness_configuration_digest="c",
            dependency_lock_digest="d",
            dataset_revision="ds",
            toolchain_identity="t",
        )
        verification = VerificationContextIdentity(
            dataset_revision="ds",
            oracle_test_patch_identity="oracle",
            fail_to_pass=(),
            pass_to_pass=(),
            harness_commit_or_digest="h",
            verification_configuration_digest="vc",
            verifier_environment_image_digest="ve",
            verifier_identity="verifier",
        )
        scope = ScopePolicyIdentity(
            allowed_scope_path_policy=("src/**",),
            protected_semantic_roles=(),
            explicit_sensitive_change_authorizations=(),
            scope_budget="budget",
            task_specific_exceptions=(),
            rule_schema_version="scope/v1",
        )
        provenance = ProvenanceAnchorIdentity(
            anchor_type="oma7",
            immutable_anchor_identifier_digest="abc",
            provenance_root="run-1",
            event_count=1,
            schema_information="prov/v1",
        )
        return Evidence(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope,
            provenance_anchor_identity=provenance,
            result=ResultStatus.PASS,
        )

    def test_state_machine_table(self) -> None:
        self.assertTrue(transition_allowed(SupervisorState.PENDING, SupervisorState.RUNNING))
        self.assertTrue(transition_allowed(SupervisorState.RUNNING, SupervisorState.VERIFYING))
        self.assertTrue(transition_allowed(SupervisorState.VERIFYING, SupervisorState.ACCEPTED, has_verification_result=True, has_valid_evidence=True))
        self.assertFalse(transition_allowed(SupervisorState.ACCEPTED, SupervisorState.RUNNING))
        self.assertFalse(transition_allowed(SupervisorState.RETRYABLE_FAILURE, SupervisorState.ACCEPTED, has_new_attempt=False))

    def test_attempt_identity_unique_and_bound(self) -> None:
        subject = SubjectIdentity(git_tree="tree", git_commit="commit", path=".")
        a1 = new_attempt_identity("run-1", 1, subject_identity=subject)
        a2 = new_attempt_identity("run-1", 2, subject_identity=subject)
        self.assertNotEqual(a1.identity(), a2.identity())
        self.assertNotEqual(a1.attempt_id, a2.attempt_id)

    def test_failure_classification_and_retry_policy(self) -> None:
        budget = RetryBudget(max_attempts=2, max_elapsed_time_seconds=30, max_execution_time_per_attempt_seconds=10)
        state = BudgetState()
        self.assertEqual(classify_failure(scope_violation=True), FailureClassification.POLICY_VIOLATION)
        self.assertEqual(classify_failure(verifier_crash=True), FailureClassification.VERIFICATION_FAILURE)
        self.assertTrue(can_retry(FailureClassification.INFRASTRUCTURE_FAILURE, budget, state, progress_exists=True, context_changed=False, attempt_number=1))
        self.assertFalse(can_retry(FailureClassification.POLICY_VIOLATION, budget, state, progress_exists=True, context_changed=True, attempt_number=1))
        self.assertFalse(can_retry(FailureClassification.VERIFICATION_FAILURE, budget, state, progress_exists=True, context_changed=True, attempt_number=1))
        self.assertFalse(can_retry(FailureClassification.BUDGET_EXHAUSTED, budget, BudgetState(attempts_used=2), progress_exists=True, context_changed=True, attempt_number=2))

    def test_retry_budget_enforced_and_pointless_retry_blocked(self) -> None:
        budget = RetryBudget(max_attempts=1, max_elapsed_time_seconds=30, max_execution_time_per_attempt_seconds=10)
        record = create_control_record(mission_id="mission-1", run_id="run-1", budget=budget)
        attempt1 = new_attempt_identity("run-1", 1, subject_identity=self.evidence().subject_identity)
        record = record.with_attempt(record_attempt := AttemptRecord(attempt_identity=attempt1, state=SupervisorState.RUNNING, current=True))
        record = record.__class__(**{**record.__dict__, "state": SupervisorState.RETRYABLE_FAILURE, "budget_state": update_budget_state(record.budget_state, attempts_delta=1)})
        attempt2 = new_attempt_identity("run-1", 2, subject_identity=self.evidence().subject_identity)
        self.assertFalse(can_start_attempt(record, next_attempt=attempt2, retry_reason=FailureClassification.INFRASTRUCTURE_FAILURE, has_changed_conditions=False))
        self.assertFalse(can_start_attempt(record, next_attempt=attempt1, retry_reason=FailureClassification.INFRASTRUCTURE_FAILURE, has_changed_conditions=False))
        exhausted = record.__class__(**{**record.__dict__, "budget_state": BudgetState(attempts_used=1, elapsed_seconds=0.0, cost_used=0)})
        self.assertEqual(exhausted.budget_state.attempts_used, 1)
        self.assertFalse(can_start_attempt(exhausted, next_attempt=attempt2, retry_reason=FailureClassification.INFRASTRUCTURE_FAILURE, has_changed_conditions=True))

    def test_budget_monotonicity(self) -> None:
        budget = RetryBudget(max_attempts=2, max_elapsed_time_seconds=10, max_execution_time_per_attempt_seconds=5)
        state = BudgetState()
        next_state = update_budget_state(state, elapsed_delta=1.5, attempts_delta=1, cost_delta=3)
        self.assertEqual(next_state.attempts_used, 1)
        self.assertEqual(next_state.elapsed_seconds, 1.5)
        self.assertEqual(next_state.cost_used, 3)
        self.assertTrue(next_state.exhausted(budget) is False)

    def test_atomic_control_record_and_resume(self) -> None:
        record = create_control_record(mission_id="mission-1", run_id="run-1", budget=RetryBudget(2, 30, 10))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            write_control_record(path, record)
            loaded = load_control_record(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.run_id, "run-1")

    def test_restart_classification(self) -> None:
        record = create_control_record(mission_id="m", run_id="r", budget=RetryBudget(2, 30, 10))
        self.assertEqual(classify_restart(record, runtime_executor_active=True), SupervisorState.RUNNING)
        self.assertEqual(classify_restart(record, frozen_submission_exists=True, verifier_complete=False), SupervisorState.VERIFYING)
        accepted = record.__class__(**{**record.__dict__, "state": SupervisorState.ACCEPTED})
        self.assertEqual(classify_restart(accepted, evidence=self.evidence()), SupervisorState.ACCEPTED)
        exhausted = record.__class__(**{**record.__dict__, "budget_state": BudgetState(attempts_used=2)})
        self.assertEqual(classify_restart(exhausted), SupervisorState.ESCALATION_REQUIRED)

    def test_control_policy_identity(self) -> None:
        policy_a = ControlPolicyIdentity(
            max_attempts=2,
            max_elapsed_time_seconds=30,
            max_execution_time_per_attempt_seconds=10,
            retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,),
            non_retryable_classifications=(FailureClassification.POLICY_VIOLATION, FailureClassification.NON_RETRYABLE),
            escalation_reasons=(EscalationReason.BUDGET_OVERRIDE_REQUIRED,),
        )
        policy_b = ControlPolicyIdentity(
            max_attempts=2,
            max_elapsed_time_seconds=30,
            max_execution_time_per_attempt_seconds=10,
            retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,),
            non_retryable_classifications=(FailureClassification.POLICY_VIOLATION, FailureClassification.NON_RETRYABLE),
            escalation_reasons=(EscalationReason.BUDGET_OVERRIDE_REQUIRED,),
        )
        policy_c = ControlPolicyIdentity(
            max_attempts=3,
            max_elapsed_time_seconds=30,
            max_execution_time_per_attempt_seconds=10,
            retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,),
            non_retryable_classifications=(FailureClassification.POLICY_VIOLATION, FailureClassification.NON_RETRYABLE),
            escalation_reasons=(EscalationReason.BUDGET_OVERRIDE_REQUIRED,),
        )
        self.assertEqual(policy_a.identity(), policy_b.identity())
        self.assertNotEqual(policy_a.identity(), policy_c.identity())

    def test_control_policy_identity_created_and_semantically_stable(self) -> None:
        base = control_policy_identity_from_policy(
            max_attempts=2,
            max_elapsed_time_seconds=30,
            max_execution_time_per_attempt_seconds=10,
            retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE, FailureClassification.VERIFICATION_FAILURE),
            non_retryable_classifications=(FailureClassification.POLICY_VIOLATION, FailureClassification.NON_RETRYABLE),
            escalation_reasons=(EscalationReason.BUDGET_OVERRIDE_REQUIRED, EscalationReason.MISSION_AMBIGUITY),
        )
        same = control_policy_identity_from_policy(
            max_attempts=2,
            max_elapsed_time_seconds=30,
            max_execution_time_per_attempt_seconds=10,
            retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE, FailureClassification.VERIFICATION_FAILURE),
            non_retryable_classifications=(FailureClassification.POLICY_VIOLATION, FailureClassification.NON_RETRYABLE),
            escalation_reasons=(EscalationReason.BUDGET_OVERRIDE_REQUIRED, EscalationReason.MISSION_AMBIGUITY),
        )
        changed_attempts = control_policy_identity_from_policy(
            max_attempts=3,
            max_elapsed_time_seconds=30,
            max_execution_time_per_attempt_seconds=10,
            retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE, FailureClassification.VERIFICATION_FAILURE),
            non_retryable_classifications=(FailureClassification.POLICY_VIOLATION, FailureClassification.NON_RETRYABLE),
            escalation_reasons=(EscalationReason.BUDGET_OVERRIDE_REQUIRED, EscalationReason.MISSION_AMBIGUITY),
        )
        changed_retry = control_policy_identity_from_policy(
            max_attempts=2,
            max_elapsed_time_seconds=30,
            max_execution_time_per_attempt_seconds=10,
            retryable_classifications=(FailureClassification.INFRASTRUCTURE_FAILURE,),
            non_retryable_classifications=(FailureClassification.POLICY_VIOLATION, FailureClassification.NON_RETRYABLE),
            escalation_reasons=(EscalationReason.BUDGET_OVERRIDE_REQUIRED, EscalationReason.MISSION_AMBIGUITY),
        )
        self.assertEqual(base.identity(), same.identity())
        self.assertNotEqual(base.identity(), changed_attempts.identity())
        self.assertNotEqual(base.identity(), changed_retry.identity())

    def test_auth_required_does_not_consume_attempt(self) -> None:
        budget = RetryBudget(max_attempts=2, max_elapsed_time_seconds=30, max_execution_time_per_attempt_seconds=10)
        record = create_control_record(mission_id="mission", run_id="run", budget=budget)
        before = record.budget_state.attempts_used
        self.assertEqual(before, 0)
        blocked = can_start_attempt(record, next_attempt=new_attempt_identity("run", 1, subject_identity=self.evidence().subject_identity), retry_reason=FailureClassification.NON_RETRYABLE, has_changed_conditions=False)
        self.assertFalse(blocked)
        self.assertEqual(record.budget_state.attempts_used, 0)

    def test_auth_required_does_not_consume_execution_attempt_and_persists_no_secrets(self) -> None:
        budget = RetryBudget(max_attempts=2, max_elapsed_time_seconds=30, max_execution_time_per_attempt_seconds=10)
        record = create_control_record(mission_id="mission", run_id="run", budget=budget)
        gate = classify_failure(auth_missing=True)
        self.assertEqual(gate, FailureClassification.NON_RETRYABLE)
        self.assertFalse(
            can_start_attempt(
                record,
                next_attempt=new_attempt_identity("run", 1, subject_identity=self.evidence().subject_identity),
                retry_reason=gate,
                has_changed_conditions=False,
            )
        )
        self.assertEqual(record.budget_state.attempts_used, 0)

    def test_synthetic_retry_recovery_acceptance(self) -> None:
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
                run_id="run-retry",
                verifier_id="verifier-1",
                cost_ledger_head="ledger-1",
                cost_ledger_event_count=1,
                scope_decision=ScopeDecision.ALLOW,
                scope_change_id="change-1",
            )
        ).identity
        evidence = Evidence(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance,
            result=ResultStatus.PASS,
            verifier_id="verifier-1",
            run_id="run-retry",
        )
        scope_eval = evaluate_scope_change(self.scope_change(), self.scope_runtime_policy(), subject_identity=subject, materialization_identity=materialization)
        observation = build_synthetic_acceptance_observation(
            evidence=evidence,
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance,
            scope_evaluation=scope_eval,
        )
        self.assertEqual(evaluate_acceptance(observation).outcome.value, "EVAL_DONE")

    def test_progress_reuse_and_stale_rejection(self) -> None:
        subject = SubjectIdentity(git_tree="tree", git_commit="commit", path=".")
        evidence = Evidence(
            subject_identity=subject,
            materialization_identity=None,
            execution_context_identity=None,
            verification_context_identity=None,
            scope_policy_identity=None,
            provenance_anchor_identity=None,
            result=ResultStatus.FAIL,
        )
        self.assertFalse(progress_is_reusable(evidence, subject, None))
        self.assertTrue(stale_progress_reuse_rejected(evidence, subject, None))

    def test_persisted_verification_reused_after_restart_and_binding_changes_fail_closed(self) -> None:
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
                run_id="run-verification",
                verifier_id="verifier-1",
                cost_ledger_head="ledger-1",
                cost_ledger_event_count=1,
                scope_decision=ScopeDecision.ALLOW,
                scope_change_id="change-1",
            )
        ).identity
        evidence = Evidence(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance,
            result=ResultStatus.PASS,
            verifier_id="verifier-1",
            run_id="run-verification",
        )
        self.assertTrue(progress_is_reusable(evidence, subject, materialization))
        mutated_subject = SubjectIdentity(git_tree="tree-mutated", git_commit="commit", path=".")
        mutated_materialization = self.materialization(mutated_subject)
        self.assertTrue(stale_progress_reuse_rejected(evidence, mutated_subject, materialization))
        self.assertTrue(stale_progress_reuse_rejected(evidence, subject, mutated_materialization))
        self.assertFalse(progress_is_reusable(evidence, mutated_subject, mutated_materialization))
        self.assertFalse(progress_is_reusable(evidence, mutated_subject, materialization))

    @unittest.skipUnless(_docker_available(), "docker CLI unavailable")
    def test_duplicate_execution_and_acceptance_prevention(self) -> None:
        evidence = self.evidence()
        self.assertTrue(duplicate_acceptance_prevented(evidence, evidence))
        self.assertTrue(duplicate_execution_prevented((record_attempt(new_attempt_identity("run-1", 1), SupervisorState.RUNNING),), "run-1"))

    def test_missing_running_container_not_treated_as_success_and_conflicts_fail_closed(self) -> None:
        budget = RetryBudget(max_attempts=2, max_elapsed_time_seconds=30, max_execution_time_per_attempt_seconds=10)
        record = create_control_record(mission_id="mission", run_id="run", budget=budget)
        attempt = AttemptRecord(attempt_identity=new_attempt_identity("run", 1, subject_identity=self.evidence().subject_identity), state=SupervisorState.RUNNING, current=True)
        record = record.with_attempt(attempt)
        record = record.__class__(**{**record.__dict__, "state": SupervisorState.RUNNING})
        self.assertEqual(classify_restart(record), SupervisorState.RETRYABLE_FAILURE)
        self.assertEqual(classify_restart(None), SupervisorState.ESCALATION_REQUIRED)
        conflict = record.__class__(**{**record.__dict__, "budget": RetryBudget(-1, 30, 10)})
        self.assertFalse(validate_control_record(conflict))
        self.assertEqual(classify_restart(conflict), SupervisorState.ESCALATION_REQUIRED)

    def test_corrupt_control_state_cases_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            base = {
                "schema_version": "oma7.supervisor-control/v1",
                "mission_id": "mission",
                "run_id": "run",
                "state": "RUNNING",
                "budget": {"max_attempts": 2, "max_elapsed_time_seconds": 30, "max_execution_time_per_attempt_seconds": 10},
                "budget_state": {"attempts_used": 0, "elapsed_seconds": 0.0, "cost_used": 0},
                "current_attempt_id": "run:1",
                "attempts": [],
                "created_at": 1.0,
                "updated_at": 1.0,
            }
            malformed_cases = [
                "{",
                "{\"schema_version\":\"oma7.supervisor-control/v9\"}",
                json.dumps({**base, "schema_version": "oma7.supervisor-control/v9"}),
                json.dumps({**base, "budget": {"max_attempts": -1, "max_elapsed_time_seconds": 30, "max_execution_time_per_attempt_seconds": 10}}),
                json.dumps({**base, "state": "UNKNOWN"}),
                json.dumps({**base, "budget_state": {"attempts_used": -1, "elapsed_seconds": 0.0, "cost_used": 0}}),
                json.dumps({**base, "current_attempt_id": None}),
                json.dumps({**base, "attempts": [{"attempt_identity": {"run_id": "run", "attempt_id": "run:1"}, "state": "RUNNING"}, {"attempt_identity": {"run_id": "run", "attempt_id": "run:1"}, "state": "RUNNING"}]}),
            ]
            for payload in malformed_cases:
                path.write_text(payload, encoding="utf-8")
                self.assertIsNone(load_control_record(path))
            self.assertIsNone(load_control_record(path))

    def test_non_retryable_failure_not_retried_and_pointless_retry_blocked(self) -> None:
        budget = RetryBudget(max_attempts=2, max_elapsed_time_seconds=30, max_execution_time_per_attempt_seconds=10)
        record = create_control_record(mission_id="mission", run_id="run", budget=budget)
        attempt = AttemptRecord(attempt_identity=new_attempt_identity("run", 1, subject_identity=self.evidence().subject_identity), state=SupervisorState.RETRYABLE_FAILURE, current=False)
        record = record.with_attempt(attempt, current=False)
        record = record.__class__(**{**record.__dict__, "state": SupervisorState.RETRYABLE_FAILURE, "budget_state": BudgetState(attempts_used=1)})
        retry_reason = classify_failure(scope_violation=True)
        self.assertEqual(retry_reason, FailureClassification.POLICY_VIOLATION)
        self.assertFalse(can_start_attempt(record, next_attempt=new_attempt_identity("run", 2, subject_identity=self.evidence().subject_identity), retry_reason=retry_reason, has_changed_conditions=False))
        self.assertFalse(can_start_attempt(record, next_attempt=new_attempt_identity("run", 1, subject_identity=self.evidence().subject_identity), retry_reason=FailureClassification.INFRASTRUCTURE_FAILURE, has_changed_conditions=False))

    def test_synthetic_retry_recovery_accepted(self) -> None:
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
                run_id="run-retry",
                verifier_id="verifier-1",
                cost_ledger_head="ledger-1",
                cost_ledger_event_count=2,
                scope_decision=ScopeDecision.ALLOW,
                scope_change_id="change-1",
            )
        ).identity
        evidence = Evidence(
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance,
            result=ResultStatus.PASS,
            verifier_id="verifier-1",
            run_id="run-retry",
        )
        scope_eval = evaluate_scope_change(self.scope_change(), self.scope_runtime_policy(), subject_identity=subject, materialization_identity=materialization)
        observation = build_synthetic_acceptance_observation(
            evidence=evidence,
            subject_identity=subject,
            materialization_identity=materialization,
            execution_context_identity=execution,
            verification_context_identity=verification,
            scope_policy_identity=scope_identity,
            provenance_anchor_identity=provenance,
            scope_evaluation=scope_eval,
        )
        decision = evaluate_acceptance(observation)
        self.assertEqual(decision.outcome.value, "EVAL_DONE")

    def test_escalation_gate(self) -> None:
        self.assertTrue(escalation_justified(repeated_retryable_failure=True))
        self.assertFalse(escalation_justified())


if __name__ == "__main__":
    unittest.main()
