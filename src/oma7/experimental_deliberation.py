from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .experimental_acceptance import E1AcceptancePrecheckReport, build_e1_acceptance_precheck_report


@dataclass(frozen=True)
class E1bMatchedDeliberationReport:
    workspace: str
    primary: E1AcceptancePrecheckReport
    secondary: E1AcceptancePrecheckReport
    matched: bool
    paused_first_real_g0: bool
    next_open_front: str
    contract_ready: bool
    match_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["primary"] = self.primary.as_dict()
        data["secondary"] = self.secondary.as_dict()
        return data


def build_e1b_matched_deliberation_report(workspace: Path) -> E1bMatchedDeliberationReport:
    primary = build_e1_acceptance_precheck_report(workspace)
    secondary = build_e1_acceptance_precheck_report(workspace)
    paused_first_real_g0 = primary.paused_first_real_g0 and secondary.paused_first_real_g0
    match_reasons = []
    if primary.acceptance.outcome != secondary.acceptance.outcome:
        match_reasons.append("acceptance outcome mismatch")
    if primary.acceptance.lifecycle_state != secondary.acceptance.lifecycle_state:
        match_reasons.append("lifecycle state mismatch")
    if primary.acceptance.reason != secondary.acceptance.reason:
        match_reasons.append("acceptance reason mismatch")
    if primary.baseline_no_op_ready != secondary.baseline_no_op_ready:
        match_reasons.append("baseline no-op readiness mismatch")
    if primary.next_open_front != secondary.next_open_front:
        match_reasons.append("next open front mismatch")
    if not paused_first_real_g0:
        match_reasons.append("paused first real G0 not preserved")
    matched = not match_reasons and primary.baseline_no_op_ready and secondary.baseline_no_op_ready
    return E1bMatchedDeliberationReport(
        workspace=str(workspace),
        primary=primary,
        secondary=secondary,
        matched=matched,
        paused_first_real_g0=paused_first_real_g0,
        next_open_front="E3 immutable submission + context evidence",
        contract_ready=matched,
        match_reasons=tuple(match_reasons),
    )
