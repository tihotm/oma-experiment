from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .experimental_acceptance import build_e1_acceptance_precheck_report
from .experimental_baseline import build_e0_baseline_report
from .experimental_deliberation import build_e1b_matched_deliberation_report


@dataclass(frozen=True)
class E2IndependentVerifierReport:
    workspace: str
    baseline_next_front: str
    acceptance_next_front: str
    deliberation_next_front: str
    paused_first_real_g0: bool
    matched: bool
    next_open_front: str
    contract_ready: bool
    match_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_e2_independent_verifier_report(workspace: Path) -> E2IndependentVerifierReport:
    baseline = build_e0_baseline_report(workspace)
    acceptance = build_e1_acceptance_precheck_report(workspace)
    deliberation = build_e1b_matched_deliberation_report(workspace)
    baseline_next = "" if baseline.next_open_front is None else baseline.next_open_front.title
    acceptance_next = acceptance.next_open_front
    deliberation_next = deliberation.next_open_front
    paused_first_real_g0 = bool(baseline.paused_fronts) and acceptance.paused_first_real_g0 and deliberation.paused_first_real_g0
    reasons = []
    if not baseline.baseline_ready:
        reasons.append("baseline report not ready")
    if not acceptance.contract_ready:
        reasons.append("acceptance precheck not ready")
    if not deliberation.contract_ready:
        reasons.append("matched deliberation not ready")
    if baseline_next != acceptance_next:
        reasons.append("baseline and acceptance next fronts differ")
    if baseline_next != deliberation_next:
        reasons.append("baseline and deliberation next fronts differ")
    if acceptance_next != deliberation_next:
        reasons.append("acceptance and deliberation next fronts differ")
    if not paused_first_real_g0:
        reasons.append("paused first real G0 not preserved")
    matched = not reasons and baseline_next == acceptance_next == deliberation_next
    return E2IndependentVerifierReport(
        workspace=str(workspace),
        baseline_next_front=baseline_next,
        acceptance_next_front=acceptance_next,
        deliberation_next_front=deliberation_next,
        paused_first_real_g0=paused_first_real_g0,
        matched=matched,
        next_open_front="E3 immutable submission + context evidence",
        contract_ready=matched,
        match_reasons=tuple(reasons),
    )
