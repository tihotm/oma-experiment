from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from .models import Evidence, ResultStatus

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


def append_evidence(run_id: str, evidence: Evidence, base_dir: str | Path = "evidence") -> None:
    ledger_file = _ledger_path(run_id, base_dir)
    current = load_evidence(run_id, base_dir)
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
                evidence = Evidence(
                    subject_identity=data.get("subject_identity"),
                    materialization_identity=data.get("materialization_identity"),
                    execution_context_identity=data.get("execution_context_identity"),
                    verification_context_identity=data.get("verification_context_identity"),
                    scope_policy_identity=data.get("scope_policy_identity"),
                    provenance_anchor_identity=data.get("provenance_anchor_identity"),
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
