from __future__ import annotations

from typing import Any

from .models import (
    Evidence,
    MaterializationIdentity,
    Observation,
    ProvenanceAnchorIdentity,
    ResultStatus,
    SCHEMA_VERSION_SUPPORTED,
    ScopePolicyIdentity,
    SubjectIdentity,
    VerificationContextIdentity,
    ExecutionContextIdentity,
)


def _normalize_status(value: Any) -> ResultStatus:
    try:
        return ResultStatus(value)
    except Exception:
        pass
    if isinstance(value, str) and value in ResultStatus.__members__:
        return ResultStatus[value]
    return ResultStatus.UNKNOWN


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} is required")
    return value


def _maybe_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    raise ValueError("expected list-like value")


def normalize_b0_observation(payload: dict[str, Any]) -> Observation:
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION_SUPPORTED:
        raise ValueError("unsupported or missing evidence schema")

    result = _normalize_status(payload.get("result"))
    if result in (ResultStatus.UNKNOWN, ResultStatus.ERROR):
        raise ValueError("unsupported evidence result")

    subject_payload = payload.get("subject_identity") or {}
    materialization_payload = payload.get("materialization_identity") or {}
    execution_payload = payload.get("execution_context_identity") or {}
    verification_payload = payload.get("verification_context_identity") or {}
    scope_payload = payload.get("scope_policy_identity") or {}
    provenance_payload = payload.get("provenance_anchor_identity") or {}

    subject = SubjectIdentity(
        git_tree=_require_string(subject_payload.get("git_tree"), "subject git_tree"),
        git_commit=subject_payload.get("git_commit"),
        path=subject_payload.get("path", "."),
        schema_version=subject_payload.get("schema_version", "oma7.subject/v1"),
    )
    materialization = MaterializationIdentity(
        subject_identity=subject,
        canonical_root_descriptor=_require_string(
            materialization_payload.get("canonical_root_descriptor"),
            "canonical_root_descriptor",
        ),
        symlink_topology=tuple(
            tuple(pair) for pair in materialization_payload.get("symlink_topology", ())
        ),
        hardlink_topology=tuple(
            tuple(pair) for pair in materialization_payload.get("hardlink_topology", ())
        ),
        worktree_reference_identity=materialization_payload.get("worktree_reference_identity"),
        mounted_reference_artifact_identities=_maybe_tuple(
            materialization_payload.get("mounted_reference_artifact_identities")
        ),
        cache_manifest_digest=materialization_payload.get("cache_manifest_digest"),
        schema_version=materialization_payload.get("schema_version", "oma7.materialization/v1"),
    )
    execution = ExecutionContextIdentity(
        environment_container_image_digest=_require_string(
            execution_payload.get("environment_container_image_digest"),
            "environment_container_image_digest",
        ),
        codex_binary_digest=_require_string(
            execution_payload.get("codex_binary_digest"),
            "codex_binary_digest",
        ),
        codex_version=_require_string(execution_payload.get("codex_version"), "codex_version"),
        model=_require_string(execution_payload.get("model"), "model"),
        reasoning_level=_require_string(execution_payload.get("reasoning_level"), "reasoning_level"),
        harness_commit_or_digest=_require_string(
            execution_payload.get("harness_commit_or_digest"),
            "harness_commit_or_digest",
        ),
        harness_configuration_digest=_require_string(
            execution_payload.get("harness_configuration_digest"),
            "harness_configuration_digest",
        ),
        dependency_lock_digest=_require_string(
            execution_payload.get("dependency_lock_digest"),
            "dependency_lock_digest",
        ),
        dataset_revision=_require_string(execution_payload.get("dataset_revision"), "dataset_revision"),
        toolchain_identity=_require_string(
            execution_payload.get("toolchain_identity"), "toolchain_identity"
        ),
        schema_version=execution_payload.get("schema_version", "oma7.execution-context/v1"),
    )
    verification = VerificationContextIdentity(
        dataset_revision=_require_string(
            verification_payload.get("dataset_revision"), "verification dataset_revision"
        ),
        oracle_test_patch_identity=_require_string(
            verification_payload.get("oracle_test_patch_identity"), "oracle_test_patch_identity"
        ),
        fail_to_pass=_maybe_tuple(verification_payload.get("fail_to_pass")),
        pass_to_pass=_maybe_tuple(verification_payload.get("pass_to_pass")),
        harness_commit_or_digest=_require_string(
            verification_payload.get("harness_commit_or_digest"), "verification harness_commit_or_digest"
        ),
        verification_configuration_digest=_require_string(
            verification_payload.get("verification_configuration_digest"),
            "verification_configuration_digest",
        ),
        verifier_environment_image_digest=verification_payload.get(
            "verifier_environment_image_digest"
        ),
        verifier_identity=verification_payload.get("verifier_identity"),
        schema_version=verification_payload.get("schema_version", "oma7.verification-context/v1"),
    )
    scope_policy = ScopePolicyIdentity(
        allowed_scope_path_policy=tuple(scope_payload.get("allowed_scope_path_policy", ())),
        protected_semantic_roles=tuple(scope_payload.get("protected_semantic_roles", ())),
        explicit_sensitive_change_authorizations=tuple(
            scope_payload.get("explicit_sensitive_change_authorizations", ())
        ),
        scope_budget=_require_string(scope_payload.get("scope_budget"), "scope_budget"),
        task_specific_exceptions=tuple(scope_payload.get("task_specific_exceptions", ())),
        rule_schema_version=_require_string(
            scope_payload.get("rule_schema_version"), "rule_schema_version"
        ),
    )
    provenance = ProvenanceAnchorIdentity(
        anchor_type=_require_string(provenance_payload.get("anchor_type"), "anchor_type"),
        immutable_anchor_identifier_digest=_require_string(
            provenance_payload.get("immutable_anchor_identifier_digest"),
            "immutable_anchor_identifier_digest",
        ),
        provenance_root=_require_string(provenance_payload.get("provenance_root"), "provenance_root"),
        event_count=provenance_payload.get("event_count"),
        schema_information=provenance_payload.get("schema_information"),
    )
    evidence = Evidence(
        subject_identity=subject,
        materialization_identity=materialization,
        execution_context_identity=execution,
        verification_context_identity=verification,
        scope_policy_identity=scope_policy,
        provenance_anchor_identity=provenance,
        result=result,
        schema_version=schema_version,
        verifier_id=payload.get("verifier_id"),
        run_id=payload.get("run_id"),
        cost_ledger_head=payload.get("cost_ledger_head"),
        cost_ledger_event_count=payload.get("cost_ledger_event_count"),
        human_intervention_summary=payload.get("human_intervention_summary"),
        predicate={k: v for k, v in payload.items() if k not in {
            "schema_version",
            "result",
            "subject_identity",
            "materialization_identity",
            "execution_context_identity",
            "verification_context_identity",
            "scope_policy_identity",
            "provenance_anchor_identity",
            "verifier_id",
            "run_id",
            "cost_ledger_head",
            "cost_ledger_event_count",
            "human_intervention_summary",
        }},
    )
    return Observation(evidence=evidence, tests_status={})
