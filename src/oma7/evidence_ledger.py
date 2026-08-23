from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from .models import Evidence, ResultStatus


POST_EXECUTION_SCHEMA = "oma7.post-execution/v1"

def _canonical(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, ResultStatus):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {name: _canonical(getattr(value, name)) for name in sorted(value.__dataclass_fields__)}
    raise TypeError(f"Unsupported ledger value: {type(value)!r}")


def _ledger_path(run_id: str, base_dir: str | Path = "evidence") -> Path:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{run_id}.jsonl"


def _serialize_entry(run_id: str, event_index: int, evidence: Evidence) -> str:
    payload = {
        "schema_version": evidence.schema_version,
        "run_id": run_id,
        "event_index": event_index,
        "evidence_identity": evidence.identity(),
        "subject_identity": _canonical(evidence.subject_identity),
        "materialization_identity": _canonical(evidence.materialization_identity),
        "execution_context_identity": _canonical(evidence.execution_context_identity),
        "verification_context_identity": _canonical(evidence.verification_context_identity),
        "scope_policy_identity": _canonical(evidence.scope_policy_identity),
        "provenance_anchor_identity": _canonical(evidence.provenance_anchor_identity),
        "result": evidence.result.value,
        "verifier_id": evidence.verifier_id,
        "cost_ledger_head": evidence.cost_ledger_head,
        "cost_ledger_event_count": evidence.cost_ledger_event_count,
        "human_intervention_summary": evidence.human_intervention_summary,
        "predicate": _canonical(evidence.predicate),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def append_evidence(run_id: str, evidence: Evidence, base_dir: str | Path = "evidence", *, expected_next_event_index: int | None = None) -> None:
    ledger_file = _ledger_path(run_id, base_dir)
    current = load_evidence(run_id, base_dir)
    if current and current[-1].identity() == evidence.identity():
        return
    for existing in current:
        if existing.identity() == evidence.identity():
            return
    if expected_next_event_index is not None and expected_next_event_index != len(current) + 1:
        raise ValueError("stale evidence ledger write rejected")
    event_index = len(current) + 1
    line = _serialize_entry(run_id, event_index, evidence)
    tmp = ledger_file.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for existing_index, existing in enumerate(current, start=1):
            fh.write(_serialize_entry(run_id, existing_index, existing) + "\n")
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(ledger_file)


def load_evidence(run_id: str, base_dir: str | Path = "evidence") -> List[Evidence]:
    ledger_file = _ledger_path(run_id, base_dir)
    if not ledger_file.exists():
        return []
    evidences: List[Evidence] = []
    expected_index = 1
    with ledger_file.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                return []
            try:
                data = json.loads(line)
            except Exception:
                return []
            if not isinstance(data, dict):
                return []
            if data.get("run_id") != run_id:
                return []
            if data.get("event_index") != expected_index:
                return []
            if data.get("schema_version") != "oma7.evidence/v1":
                return []
            try:
                from .control_plane import _load_subject_identity, _load_materialization_identity, _load_execution_context_identity, _load_scope_policy_identity
                # We need to construct VerificationContextIdentity and ProvenanceAnchorIdentity manually because
                # they aren't loaded in full by _load_* (or we can just construct them if they exist).
                v_data = data.get("verification_context_identity")
                verification_context_identity = None
                if v_data is not None:
                    from .models import VerificationContextIdentity
                    verification_context_identity = VerificationContextIdentity(
                        dataset_revision=v_data["dataset_revision"],
                        oracle_test_patch_identity=v_data["oracle_test_patch_identity"],
                        fail_to_pass=tuple(v_data.get("fail_to_pass", ())),
                        pass_to_pass=tuple(v_data.get("pass_to_pass", ())),
                        harness_commit_or_digest=v_data["harness_commit_or_digest"],
                        verification_configuration_digest=v_data["verification_configuration_digest"],
                        verifier_environment_image_digest=v_data.get("verifier_environment_image_digest"),
                        verifier_identity=v_data.get("verifier_identity"),
                        schema_version=v_data.get("schema_version", "oma7.verification-context/v1")
                    )
                p_data = data.get("provenance_anchor_identity")
                provenance_anchor_identity = None
                if p_data is not None:
                    from .models import ProvenanceAnchorIdentity
                    provenance_anchor_identity = ProvenanceAnchorIdentity(
                        anchor_type=p_data["anchor_type"],
                        immutable_anchor_identifier_digest=p_data["immutable_anchor_identifier_digest"],
                        provenance_root=p_data["provenance_root"],
                        event_count=p_data.get("event_count"),
                        schema_information=p_data.get("schema_information")
                    )

                evidence = Evidence(
                    subject_identity=_load_subject_identity(data.get("subject_identity")),
                    materialization_identity=_load_materialization_identity(data.get("materialization_identity")),
                    execution_context_identity=_load_execution_context_identity(data.get("execution_context_identity")),
                    verification_context_identity=verification_context_identity,
                    scope_policy_identity=_load_scope_policy_identity(data.get("scope_policy_identity")),
                    provenance_anchor_identity=provenance_anchor_identity,
                    result=ResultStatus(data.get("result")),
                    schema_version=data.get("schema_version"),
                    verifier_id=data.get("verifier_id"),
                    run_id=data.get("run_id"),
                    cost_ledger_head=data.get("cost_ledger_head"),
                    cost_ledger_event_count=data.get("cost_ledger_event_count"),
                    human_intervention_summary=data.get("human_intervention_summary"),
                    predicate=data.get("predicate", {}),
                )
                evidences.append(evidence)
            except Exception:
                return []
            expected_index += 1
    return evidences


def append_post_execution_record(run_id: str, record: object, base_dir: str | Path = "evidence", *, expected_next_event_index: int | None = None) -> None:
    ledger_file = _ledger_path(f"{run_id}.post-execution", base_dir)
    current = load_post_execution_records(run_id, base_dir)
    record_payload = _canonical(record)
    for existing in current:
        if existing.get("record") == record_payload:
            return
    if expected_next_event_index is not None and expected_next_event_index != len(current) + 1:
        raise ValueError("stale post-execution ledger write rejected")
    event_index = len(current) + 1
    payload = {"schema_version": POST_EXECUTION_SCHEMA, "run_id": run_id, "event_index": event_index, "record": record_payload}
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    tmp = ledger_file.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for existing_index, existing in enumerate(current, start=1):
            fh.write(json.dumps(existing, ensure_ascii=False, sort_keys=True) + "\n")
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(ledger_file)


def load_post_execution_records(run_id: str, base_dir: str | Path = "evidence") -> List[dict[str, object]]:
    ledger_file = _ledger_path(f"{run_id}.post-execution", base_dir)
    if not ledger_file.exists():
        return []
    records: List[dict[str, object]] = []
    expected_index = 1
    with ledger_file.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                return []
            try:
                data = json.loads(line)
            except Exception:
                return []
            if not isinstance(data, dict):
                return []
            if data.get("run_id") != run_id:
                return []
            if data.get("event_index") != expected_index:
                return []
            if data.get("schema_version") != POST_EXECUTION_SCHEMA:
                return []
            records.append(data)
            expected_index += 1
    return records
