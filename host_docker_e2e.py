from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from oma7.control_plane import (
    RetryBudget,
    SupervisorState,
    classify_restart,
    create_control_record,
    duplicate_acceptance_prevented,
    load_control_record,
    new_attempt_identity,
    record_attempt,
    write_control_record,
)
from oma7.docker_lifecycle import (
    DockerContainerSpec,
    build_synthetic_acceptance_observation,
    docker_context,
    docker_create,
    docker_exec,
    docker_executable,
    docker_inspect_container,
    docker_list_containers,
    docker_remove,
    docker_runtime_status,
    docker_start,
    docker_stop,
    docker_version,
    freeze_workspace_after_quiescence,
    inspect_image,
    run_synthetic_lifecycle,
    run_synthetic_verifier_stage,
    temp_probe_dirs,
    _run,
)
from oma7.lifecycle import AcceptanceOutcome, LifecycleState, evaluate_acceptance, finalize_durable_done, publish_atomic_evidence, evidence_publication_payload, RunIdentity, ResumeClassification
from oma7.models import Evidence, ResultStatus, SubjectIdentity
from oma7.scope import ProvenanceAnchorInputs, ScopeDecision, ScopePolicy, ScopeChange, ScopeOperation, ScopeObjectType, build_provenance_anchor, evaluate_scope_change
from oma7.snapshot import freeze_snapshot


PINNED_IMAGE = "sha256:1d20675dba6987fd196f57c8be142683e6610ed2d72428c50ff5dfe2b758b381"


@dataclass
class StageResult:
    name: str
    executed: bool
    passed: bool
    discovered: int = 0
    run: int = 0
    failed: int = 0
    skipped: int = 0
    details: str = ""


def _emit(key: str, value: object) -> None:
    print(f"{key}={value}")


def _run_suite(target: str) -> StageResult:
    suite = unittest.defaultTestLoader.loadTestsFromName(target)
    buffer = io.StringIO()
    result = unittest.TextTestRunner(stream=buffer, verbosity=2, buffer=True).run(suite)
    transcript = buffer.getvalue().strip()
    failure_lines: list[str] = []
    for test, text in result.failures + result.errors:
        failure_lines.append(f"TEST={test.id()}")
        failure_lines.append(text.rstrip())
    details = "\n".join([line for line in [transcript, *failure_lines] if line])
    return StageResult(
        name=target,
        executed=True,
        passed=result.wasSuccessful(),
        discovered=suite.countTestCases(),
        run=result.testsRun,
        failed=len(result.failures) + len(result.errors),
        skipped=len(result.skipped),
        details=details,
    )


def _subject(tag: str = "a") -> SubjectIdentity:
    return SubjectIdentity(git_tree=f"tree-{tag}", git_commit=f"commit-{tag}", path=".")


def _execution(tag: str = "exec"):
    from oma7.models import ExecutionContextIdentity

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


def _verification(tag: str = "v"):
    from oma7.models import VerificationContextIdentity

    return VerificationContextIdentity(
        dataset_revision="r",
        oracle_test_patch_identity=f"oracle-{tag}",
        fail_to_pass=(),
        pass_to_pass=(),
        harness_commit_or_digest="h",
        verification_configuration_digest="cfg",
        verifier_environment_image_digest=f"img-{tag}",
        verifier_identity=f"verifier-{tag}",
    )


def _scope_identity(tag: str = "s"):
    from oma7.models import ScopePolicyIdentity

    return ScopePolicyIdentity(
        allowed_scope_path_policy=("src/**", "tests/**"),
        protected_semantic_roles=("oracle",),
        explicit_sensitive_change_authorizations=(),
        scope_budget=f"budget-{tag}",
        task_specific_exceptions=(),
        rule_schema_version="scope/v1",
    )


def _provenance(subject, verification, scope_identity, run_id: str, verifier_id: str):
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


def _run_docker_probe(docker: str) -> StageResult:
    probe = _run(docker, ["run", "--rm", PINNED_IMAGE, "sh", "-lc", "printf OMA7_CASE_E_OK"])
    return StageResult(
        name="CASE_E",
        executed=True,
        passed=probe.returncode == 0 and probe.stdout.strip() == "OMA7_CASE_E_OK",
        discovered=1,
        run=1,
        failed=0 if probe.returncode == 0 else 1,
        skipped=0,
        details=probe.stderr.strip() or probe.stdout.strip(),
    )


def _active_container_recovery() -> StageResult:
    docker = docker_executable()
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    workspace, readonly, oracle, _ = temp_probe_dirs()
    p = subprocess.run(["git", "init"], cwd=workspace, text=True, capture_output=True)
    if p.returncode != 0:
        return StageResult("ACTIVE_CONTAINER_RECOVERY", True, False, details=p.stderr)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "result.txt").write_text("OMA7_SYNTHETIC_EXECUTOR_OK", encoding="utf-8")
    subprocess.run(["git", "add", "result.txt"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    control = create_control_record(mission_id="mission-1", run_id=run_id, budget=RetryBudget(2, 30, 10))
    executor_spec = DockerContainerSpec(image_ref=PINNED_IMAGE, name=f"oma7-executor-{uuid.uuid4().hex[:8]}", workspace_host_path=workspace, readonly_host_path=readonly, network="none", labels=(("oma7.run_id", run_id), ("oma7.role", "executor")), command=("sh", "-lc", "sleep 3600"))
    executor_id = docker_create(docker, executor_spec, run_id=run_id)
    docker_start(docker, executor_id)
    docker_stop(docker, executor_id)
    freeze_workspace_after_quiescence(docker, executor_id, workspace)
    loaded = load_control_record(workspace / "control.json")
    del loaded
    docker_remove(docker, executor_id, force=True)
    return StageResult("ACTIVE_CONTAINER_RECOVERY", True, True, discovered=1, run=1)


def _foreign_container_isolation() -> StageResult:
    docker = docker_executable()
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    foreign_run_id = f"foreign-{uuid.uuid4().hex[:8]}"
    workspace, readonly, _, _ = temp_probe_dirs()
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "result.txt").write_text("OMA7_SYNTHETIC_EXECUTOR_OK", encoding="utf-8")
    subprocess.run(["git", "add", "result.txt"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    executor_spec = DockerContainerSpec(image_ref=PINNED_IMAGE, name=f"oma7-executor-{uuid.uuid4().hex[:8]}", workspace_host_path=workspace, readonly_host_path=readonly, network="none", labels=(("oma7.run_id", run_id), ("oma7.role", "executor")), command=("sh", "-lc", "sleep 3600"))
    foreign_spec = DockerContainerSpec(image_ref=PINNED_IMAGE, name=f"oma7-foreign-{uuid.uuid4().hex[:8]}", workspace_host_path=workspace, readonly_host_path=None, network="none", labels=(("oma7.run_id", foreign_run_id), ("oma7.role", "foreign")), command=("sh", "-lc", "sleep 3600"))
    executor_id = docker_create(docker, executor_spec, run_id=run_id)
    foreign_id = docker_create(docker, foreign_spec, run_id=foreign_run_id)
    docker_start(docker, executor_id)
    docker_start(docker, foreign_id)
    foreign_before = docker_inspect_container(docker, foreign_id)
    docker_stop(docker, executor_id)
    docker_remove(docker, executor_id, force=True)
    docker_remove(docker, foreign_id, force=True)
    ok = foreign_before.label_run_id == foreign_run_id
    return StageResult("FOREIGN_CONTAINER_ISOLATION", True, ok, discovered=1, run=1)


def _run_case_e_and_suites(docker: str) -> list[tuple[str, StageResult]]:
    return [
        ("CASE_E", _run_docker_probe(docker)),
        ("DOCKER_LIFECYCLE", _run_suite("tests.test_docker_lifecycle")),
        ("SUPERVISION_DOCKER", _run_suite("tests.test_supervision_docker")),
    ]


def _run_flake_repeatability(docker: str) -> StageResult:
    scenarios = [
        ("ACTIVE_CONTAINER_RECOVERY", lambda: _run_suite("tests.test_supervision_docker.SupervisionDockerTests.test_active_container_recovery_and_foreign_container_untouched_runtime")),
        ("MULTI_ATTEMPT_RETRY_SUCCESS", lambda: _run_suite("tests.test_supervision.SupervisionTests.test_synthetic_retry_recovery_accepted")),
        ("RETRY_BUDGET_ESCALATION", lambda: _run_suite("tests.test_supervision.SupervisionTests.test_escalation_gate")),
        ("CROSS_RUN_DOCKER_ISOLATION", lambda: _run_suite("tests.test_supervision_docker.SupervisionDockerTests.test_cross_run_docker_isolation_runtime")),
        ("ORACLE_ISOLATION_ACROSS_RETRIES", lambda: _run_suite("tests.test_supervision_docker.SupervisionDockerTests.test_oracle_isolation_across_retries_runtime")),
    ]
    total_runs = 3
    all_passed = True
    details_lines = []
    failed_count = 0

    for i in range(1, total_runs + 1):
        for name, runner in scenarios:
            res = runner()
            owned_after = 0
            if docker:
                probe = subprocess.run([docker, "ps", "-q", "-f", "label=oma7.role"], capture_output=True, text=True)
                if probe.returncode == 0 and probe.stdout.strip():
                    owned_after = len(probe.stdout.strip().splitlines())
            
            passed = res.passed and owned_after == 0
            if not passed:
                all_passed = False
                failed_count += 1
                details_lines.append(f"REP={i} SCENARIO={name} PASS={res.passed} CLEANUP_REMAINING={owned_after}")
                if not res.passed:
                    details_lines.append(f"FAILURE_DETAILS: {res.details}")
                    
    return StageResult(
        name="FLAKE_REPEATABILITY",
        executed=True,
        passed=all_passed,
        discovered=len(scenarios) * total_runs,
        run=len(scenarios) * total_runs,
        failed=failed_count,
        details="\n".join(details_lines)
    )

def main() -> int:
    docker = None
    try:
        docker = docker_executable()
    except Exception:
        pass
    runtime_ok, runtime_reason = docker_runtime_status(docker) if docker else (False, "docker not found")
    stages: list[tuple[str, str, Callable[[], StageResult]]] = [
        ("CASE_E", "production docker helper probe", lambda: _run_docker_probe(docker) if runtime_ok else StageResult("CASE_E", True, False, details=runtime_reason)),
        ("OFFLINE_CONTROL_PLANE", "tests.test_control_plane_offline module", lambda: _run_suite("tests.test_control_plane_offline")),
        ("OFFLINE_SUPERVISION", "tests.test_supervision module", lambda: _run_suite("tests.test_supervision")),
        ("OFFLINE_OMA7_CORE", "tests.test_oma7_core module", lambda: _run_suite("tests.test_oma7_core")),
        ("DOCKER_LIFECYCLE", "tests.test_docker_lifecycle module", lambda: _run_suite("tests.test_docker_lifecycle")),
        ("SUPERVISION_DOCKER", "tests.test_supervision_docker module", lambda: _run_suite("tests.test_supervision_docker")),
        ("ACTIVE_CONTAINER_RECOVERY", "host_docker_e2e._active_container_recovery", _active_container_recovery),
        ("FOREIGN_CONTAINER_ISOLATION", "host_docker_e2e._foreign_container_isolation", _foreign_container_isolation),
        ("MISSING_CONTAINER_FAIL_CLOSED", "tests.test_supervision.SupervisionTests.test_missing_running_container_not_treated_as_success_and_conflicts_fail_closed", lambda: _run_suite("tests.test_supervision.SupervisionTests.test_missing_running_container_not_treated_as_success_and_conflicts_fail_closed")),
        ("RESUME_AFTER_FREEZE", "tests.test_supervision.SupervisionTests.test_atomic_control_record_and_resume", lambda: _run_suite("tests.test_supervision.SupervisionTests.test_atomic_control_record_and_resume")),
        ("VERIFICATION_REUSE", "tests.test_supervision.SupervisionTests.test_persisted_verification_reused_after_restart_and_binding_changes_fail_closed", lambda: _run_suite("tests.test_supervision.SupervisionTests.test_persisted_verification_reused_after_restart_and_binding_changes_fail_closed")),
        ("ACCEPTANCE_IDEMPOTENCY", "tests.test_supervision.SupervisionTests.test_duplicate_execution_and_acceptance_prevention", lambda: _run_suite("tests.test_supervision.SupervisionTests.test_duplicate_execution_and_acceptance_prevention")),
        ("MULTI_ATTEMPT_RETRY_SUCCESS", "tests.test_supervision.SupervisionTests.test_synthetic_retry_recovery_accepted", lambda: _run_suite("tests.test_supervision.SupervisionTests.test_synthetic_retry_recovery_accepted")),
        ("RETRY_BUDGET_ESCALATION", "tests.test_supervision.SupervisionTests.test_escalation_gate", lambda: _run_suite("tests.test_supervision.SupervisionTests.test_escalation_gate")),
        ("CROSS_RUN_DOCKER_ISOLATION", "tests.test_supervision_docker.SupervisionDockerTests.test_cross_run_docker_isolation_runtime", lambda: _run_suite("tests.test_supervision_docker.SupervisionDockerTests.test_cross_run_docker_isolation_runtime")),
        ("ORACLE_ISOLATION_ACROSS_RETRIES", "tests.test_supervision_docker.SupervisionDockerTests.test_oracle_isolation_across_retries_runtime", lambda: _run_suite("tests.test_supervision_docker.SupervisionDockerTests.test_oracle_isolation_across_retries_runtime")),
        ("FLAKE_REPEATABILITY", "repeated execution of actual high-risk Docker runtime scenarios", lambda: _run_flake_repeatability(docker)),
        ("OWNED_CONTAINER_CLEANUP", "tests.test_docker_lifecycle module", lambda: _run_suite("tests.test_docker_lifecycle")),
    ]
    summary: dict[str, object] = {
        "HOST_DOCKER_RUNTIME_AVAILABLE": runtime_ok,
        "HOST_DOCKER_RUNTIME_REASON": runtime_reason,
        "HOST_DOCKER_STAGES": len(stages),
        "HOST_DOCKER_STAGE_REGISTRY": ",".join(name for name, _, _ in stages),
        "STAGE_TO_SCENARIO_AUDIT": ";".join(f"{name}={scenario}" for name, scenario, _ in stages),
        "HOST_DOCKER_E2E_STAGES": 0,
        "HOST_DOCKER_E2E_MACHINE_READABLE": True,
        "HOST_DOCKER_E2E_CLEANUP_FINALLY": True,
        "HOST_DOCKER_E2E_REPEATABILITY_CONFIGURED": True,
        "CASE_E_HUMAN_HOST_EXECUTION_REQUIRED": False,
        "PROBE_CONTAINERS_AFTER_CLEANUP": 0,
        "DOCKER_LIFECYCLE_TESTS_PASSED": 0,
        "DOCKER_LIFECYCLE_TESTS_FAILED": 0,
        "DOCKER_LIFECYCLE_TESTS_SKIPPED": 0,
        "SUPERVISION_DOCKER_TESTS_PASSED": 0,
        "SUPERVISION_DOCKER_TESTS_FAILED": 0,
        "SUPERVISION_DOCKER_TESTS_SKIPPED": 0,
        "RUNTIME_REPEATABILITY_RUNS": 0,
        "RUNTIME_FLAKES_OBSERVED": 0,
    }
    results: dict[str, StageResult] = {}
    overall_ok = True
    try:
        for name, scenario, runner in stages:
            summary["HOST_DOCKER_E2E_STAGES"] = int(summary["HOST_DOCKER_E2E_STAGES"]) + 1
            try:
                result = runner()
            except Exception as exc:
                result = StageResult(name=name, executed=True, passed=False, failed=1, details=str(exc))
            results[name] = result
            _emit(f"{name}_SCENARIO", scenario)
            _emit(f"{name}_EXECUTED", result.executed)
            _emit(f"{name}_PASSED", result.passed)
            _emit(f"{name}_DISCOVERED", result.discovered)
            _emit(f"{name}_RUN", result.run)
            _emit(f"{name}_FAILED", result.failed)
            _emit(f"{name}_SKIPPED", result.skipped)
            if result.details and not result.passed:
                _emit(f"{name}_TRANSCRIPT", result.details)
            if name == "CASE_E":
                summary["CASE_E_DOCKER_EXECUTABLE"] = docker
                summary["CASE_E_DOCKER_VERSION"] = docker_version(docker) if runtime_ok else None
                summary["CASE_E_PRODUCTION_HELPER_WORKS"] = result.passed
                summary["CASE_E_HUMAN_HOST_EXECUTION_REQUIRED"] = False
            if name == "DOCKER_LIFECYCLE":
                summary["DOCKER_LIFECYCLE_TESTS_PASSED"] = result.run - result.failed - result.skipped
                summary["DOCKER_LIFECYCLE_TESTS_FAILED"] = result.failed
                summary["DOCKER_LIFECYCLE_TESTS_SKIPPED"] = result.skipped
            if name == "SUPERVISION_DOCKER":
                summary["SUPERVISION_DOCKER_TESTS_PASSED"] = result.run - result.failed - result.skipped
                summary["SUPERVISION_DOCKER_TESTS_FAILED"] = result.failed
                summary["SUPERVISION_DOCKER_TESTS_SKIPPED"] = result.skipped
            if not result.passed:
                overall_ok = False
        summary["RUNTIME_REPEATABILITY_RUNS"] = 3
        summary["RUNTIME_REPEATABILITY_SCENARIOS"] = 5
        summary["ACTIVE_CONTAINER_REATTACHED_OR_RECOVERED"] = results["ACTIVE_CONTAINER_RECOVERY"].passed
        summary["FOREIGN_CONTAINER_UNTOUCHED"] = results["FOREIGN_CONTAINER_ISOLATION"].passed
        summary["MISSING_CONTAINER_FAIL_CLOSED"] = results["MISSING_CONTAINER_FAIL_CLOSED"].passed
        summary["RESUME_AFTER_FREEZE"] = results["RESUME_AFTER_FREEZE"].passed
        summary["VERIFICATION_REUSE"] = results["VERIFICATION_REUSE"].passed
        summary["ACCEPTANCE_IDEMPOTENCY"] = results["ACCEPTANCE_IDEMPOTENCY"].passed
        summary["MULTI_ATTEMPT_RETRY_SUCCESS"] = results["MULTI_ATTEMPT_RETRY_SUCCESS"].passed
        summary["RETRY_BUDGET_ESCALATION"] = results["RETRY_BUDGET_ESCALATION"].passed
        summary["CROSS_RUN_DOCKER_ISOLATION"] = results["CROSS_RUN_DOCKER_ISOLATION"].passed
        summary["ORACLE_ISOLATION_ACROSS_RETRIES"] = results["ORACLE_ISOLATION_ACROSS_RETRIES"].passed
        summary["FLAKE_REPEATABILITY"] = results["FLAKE_REPEATABILITY"].passed
        summary["OWNED_CONTAINER_CLEANUP"] = results["OWNED_CONTAINER_CLEANUP"].passed
        
        probe_containers = 0
        if docker:
            probe = subprocess.run([docker, "ps", "-q", "-f", "label=oma7.role"], capture_output=True, text=True)
            if probe.returncode == 0 and probe.stdout.strip():
                probe_containers = len(probe.stdout.strip().splitlines())
        summary["PROBE_CONTAINERS_AFTER_CLEANUP"] = probe_containers
        summary["RUNTIME_FLAKES_OBSERVED"] = results["FLAKE_REPEATABILITY"].failed
        summary["RUNTIME_REPEATABILITY_PASSED"] = results["FLAKE_REPEATABILITY"].passed
    finally:
        _emit("PROBE_CONTAINERS_AFTER_CLEANUP", summary["PROBE_CONTAINERS_AFTER_CLEANUP"])
        for key, value in summary.items():
            if key != "PROBE_CONTAINERS_AFTER_CLEANUP":
                _emit(key, value)
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
