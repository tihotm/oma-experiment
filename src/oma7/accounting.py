from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from hashlib import sha256
from pathlib import Path
from time import time
from typing import Any


ACCOUNTING_SCHEMA_VERSION = "oma7.accounting/v1"


class AccountingEventKind(str, Enum):
    EXECUTION = "EXECUTION"
    VERIFICATION = "VERIFICATION"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    HUMAN_OVERRIDE = "HUMAN_OVERRIDE"
    HUMAN_INTERVENTION = "HUMAN_INTERVENTION"


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if hasattr(value, "__dataclass_fields__"):
        return {name: _canonical(getattr(value, name)) for name in sorted(value.__dataclass_fields__) if getattr(value, name) is not None}
    raise TypeError(f"Unsupported accounting value: {type(value)!r}")


def _digest(payload: Any) -> str:
    raw = json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CostLedgerEntry:
    run_id: str
    event_index: int
    kind: AccountingEventKind
    cost_units: int
    reason: str | None = None
    human_actor: str | None = None
    evidence_reference: str | None = None
    schema_version: str = ACCOUNTING_SCHEMA_VERSION
    created_at: float = 0.0

    def is_valid(self) -> bool:
        return bool(self.run_id) and self.event_index > 0 and self.cost_units >= 0

    def identity(self) -> str:
        if not self.is_valid():
            raise ValueError("cost ledger entry requires valid run, index, and cost")
        payload = {
            "run_id": self.run_id,
            "kind": self.kind,
            "cost_units": self.cost_units,
            "reason": self.reason,
            "human_actor": self.human_actor,
            "evidence_reference": self.evidence_reference,
            "schema_version": self.schema_version,
        }
        return _digest(payload)


@dataclass(frozen=True)
class HumanInterventionRecord:
    run_id: str
    event_index: int
    kind: AccountingEventKind
    human_actor: str
    reason: str
    approved: bool
    evidence_reference: str | None = None
    schema_version: str = ACCOUNTING_SCHEMA_VERSION
    created_at: float = 0.0

    def is_valid(self) -> bool:
        return bool(self.run_id) and self.event_index > 0 and bool(self.human_actor) and bool(self.reason)

    def identity(self) -> str:
        if not self.is_valid():
            raise ValueError("human intervention record requires valid actor and reason")
        payload = {
            "run_id": self.run_id,
            "kind": self.kind,
            "human_actor": self.human_actor,
            "reason": self.reason,
            "approved": self.approved,
            "evidence_reference": self.evidence_reference,
            "schema_version": self.schema_version,
        }
        return _digest(payload)


@dataclass(frozen=True)
class AccountingLedger:
    run_id: str
    entries: tuple[CostLedgerEntry, ...] = ()
    human_interventions: tuple[HumanInterventionRecord, ...] = ()
    schema_version: str = ACCOUNTING_SCHEMA_VERSION

    def is_valid(self) -> bool:
        if not self.run_id:
            return False
        expected = 1
        for entry in self.entries:
            if entry.run_id != self.run_id or entry.event_index != expected or not entry.is_valid():
                return False
            expected += 1
        expected = 1
        for record in self.human_interventions:
            if record.run_id != self.run_id or record.event_index != expected or not record.is_valid():
                return False
            expected += 1
        return True

    def head(self) -> str:
        if not self.is_valid():
            raise ValueError("accounting ledger is not valid")
        return _digest(
            {
                "run_id": self.run_id,
                "entries": self.entries,
                "human_interventions": self.human_interventions,
                "schema_version": self.schema_version,
            }
        )

    def event_count(self) -> int:
        if not self.is_valid():
            raise ValueError("accounting ledger is not valid")
        return len(self.entries) + len(self.human_interventions)

    def find_entry(self, identity: str) -> CostLedgerEntry | None:
        for entry in self.entries:
            if entry.identity() == identity:
                return entry
        return None

    def find_human_intervention(self, identity: str) -> HumanInterventionRecord | None:
        for record in self.human_interventions:
            if record.identity() == identity:
                return record
        return None


def _ledger_dir(base_dir: str | Path = "evidence") -> Path:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base / "accounting"


def _ledger_path(run_id: str, base_dir: str | Path = "evidence") -> Path:
    return _ledger_dir(base_dir) / f"{run_id}.jsonl"


def _serialize(record: CostLedgerEntry | HumanInterventionRecord) -> str:
    return json.dumps(_canonical(record), ensure_ascii=False, sort_keys=True)


def append_cost_entry(
    run_id: str,
    *,
    cost_units: int,
    kind: AccountingEventKind = AccountingEventKind.EXECUTION,
    reason: str | None = None,
    human_actor: str | None = None,
    evidence_reference: str | None = None,
    base_dir: str | Path = "evidence",
    expected_next_event_index: int | None = None,
) -> CostLedgerEntry:
    ledger = load_accounting_ledger(run_id, base_dir)
    pending = CostLedgerEntry(
        run_id=run_id,
        event_index=len(ledger.entries) + 1,
        kind=kind,
        cost_units=cost_units,
        reason=reason,
        human_actor=human_actor,
        evidence_reference=evidence_reference,
        created_at=time(),
    )
    existing = ledger.find_entry(pending.identity())
    if existing is not None:
        return existing
    if expected_next_event_index is not None and expected_next_event_index != len(ledger.entries) + 1:
        raise ValueError("stale cost ledger write rejected")
    if not pending.is_valid():
        raise ValueError("invalid cost ledger entry")
    _append_record(run_id, pending, base_dir)
    return pending


def append_human_intervention(
    run_id: str,
    *,
    human_actor: str,
    reason: str,
    approved: bool,
    kind: AccountingEventKind = AccountingEventKind.HUMAN_INTERVENTION,
    evidence_reference: str | None = None,
    base_dir: str | Path = "evidence",
    expected_next_event_index: int | None = None,
) -> HumanInterventionRecord:
    ledger = load_accounting_ledger(run_id, base_dir)
    pending = HumanInterventionRecord(
        run_id=run_id,
        event_index=len(ledger.human_interventions) + 1,
        kind=kind,
        human_actor=human_actor,
        reason=reason,
        approved=approved,
        evidence_reference=evidence_reference,
        created_at=time(),
    )
    existing = ledger.find_human_intervention(pending.identity())
    if existing is not None:
        return existing
    if expected_next_event_index is not None and expected_next_event_index != len(ledger.human_interventions) + 1:
        raise ValueError("stale human intervention write rejected")
    if not pending.is_valid():
        raise ValueError("invalid human intervention record")
    _append_record(run_id, pending, base_dir)
    return pending


def _append_record(run_id: str, record: CostLedgerEntry | HumanInterventionRecord, base_dir: str | Path = "evidence") -> Path:
    ledger_path = _ledger_path(run_id, base_dir)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = ledger_path.with_suffix(".tmp")
    current_lines: list[str] = []
    current_ledger = load_accounting_ledger(run_id, base_dir)
    if ledger_path.exists():
        raw_text = ledger_path.read_text(encoding="utf-8")
        if raw_text.strip() and current_ledger.event_count() == 0:
            raise ValueError("existing accounting ledger is invalid")
        current_lines = raw_text.splitlines()
    with tmp.open("w", encoding="utf-8") as fh:
        for existing in current_lines:
            if existing.strip():
                fh.write(existing.rstrip("\n") + "\n")
        fh.write(_serialize(record) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(ledger_path)
    return ledger_path


def load_accounting_ledger(run_id: str, base_dir: str | Path = "evidence") -> AccountingLedger:
    ledger_path = _ledger_path(run_id, base_dir)
    if not ledger_path.exists():
        return AccountingLedger(run_id=run_id)
    entries: list[CostLedgerEntry] = []
    human_interventions: list[HumanInterventionRecord] = []
    expected_cost_index = 1
    expected_human_index = 1
    with ledger_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                return AccountingLedger(run_id=run_id)
            try:
                data = json.loads(line)
            except Exception:
                return AccountingLedger(run_id=run_id)
            if not isinstance(data, dict) or data.get("run_id") != run_id:
                return AccountingLedger(run_id=run_id)
            schema_version = data.get("schema_version")
            if schema_version != ACCOUNTING_SCHEMA_VERSION:
                return AccountingLedger(run_id=run_id)
            try:
                kind = AccountingEventKind(data["kind"])
                if kind in {
                    AccountingEventKind.HUMAN_APPROVAL,
                    AccountingEventKind.HUMAN_ESCALATION,
                    AccountingEventKind.HUMAN_OVERRIDE,
                    AccountingEventKind.HUMAN_INTERVENTION,
                }:
                    record = HumanInterventionRecord(
                        run_id=data["run_id"],
                        event_index=data["event_index"],
                        kind=kind,
                        human_actor=data["human_actor"],
                        reason=data["reason"],
                        approved=bool(data["approved"]),
                        evidence_reference=data.get("evidence_reference"),
                        schema_version=schema_version,
                        created_at=data.get("created_at", 0.0),
                    )
                    if record.event_index != expected_human_index:
                        return AccountingLedger(run_id=run_id)
                    expected_human_index += 1
                    human_interventions.append(record)
                else:
                    entry = CostLedgerEntry(
                        run_id=data["run_id"],
                        event_index=data["event_index"],
                        kind=kind,
                        cost_units=data["cost_units"],
                        reason=data.get("reason"),
                        human_actor=data.get("human_actor"),
                        evidence_reference=data.get("evidence_reference"),
                        schema_version=schema_version,
                        created_at=data.get("created_at", 0.0),
                    )
                    if entry.event_index != expected_cost_index:
                        return AccountingLedger(run_id=run_id)
                    expected_cost_index += 1
                    entries.append(entry)
            except Exception:
                return AccountingLedger(run_id=run_id)
    return AccountingLedger(run_id=run_id, entries=tuple(entries), human_interventions=tuple(human_interventions))


def cost_ledger_head(run_id: str, base_dir: str | Path = "evidence") -> str | None:
    ledger_path = _ledger_path(run_id, base_dir)
    if not ledger_path.exists():
        return None
    ledger = load_accounting_ledger(run_id, base_dir)
    if not ledger.is_valid():
        return None
    if ledger.event_count() == 0:
        return None
    return ledger.head()


def cost_ledger_event_count(run_id: str, base_dir: str | Path = "evidence") -> int:
    ledger = load_accounting_ledger(run_id, base_dir)
    if not ledger.is_valid():
        return 0
    return ledger.event_count()


def human_intervention_summary(run_id: str, base_dir: str | Path = "evidence") -> str | None:
    ledger = load_accounting_ledger(run_id, base_dir)
    if not ledger.is_valid():
        return None
    if not ledger.human_interventions:
        return None
    approved = sum(1 for item in ledger.human_interventions if item.approved)
    blocked = len(ledger.human_interventions) - approved
    return f"approved={approved};blocked={blocked};total={len(ledger.human_interventions)}"
