from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExperimentalFront:
    index: int
    title: str
    status: str


@dataclass(frozen=True)
class E0BaselineReport:
    workspace: str
    current_state_head: str
    scientific_counters: dict[str, int | str]
    paused_fronts: tuple[ExperimentalFront, ...]
    next_open_front: ExperimentalFront | None
    baseline_ready: bool
    baseline_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_engineering_roadmap(root: Path) -> tuple[ExperimentalFront, ...]:
    roadmap = root / "docs" / "ROADMAP.md"
    items: list[ExperimentalFront] = []
    in_engineering = False
    index = 0
    for raw_line in roadmap.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.lower() == "## engineering roadmap":
            in_engineering = True
            continue
        if not in_engineering:
            continue
        if not line or not line[0].isdigit():
            continue
        title = line.split(".", 1)[1].strip() if "." in line else line
        status = "OPEN"
        if title.lower() == "governance freeze":
            status = "COMPLETE"
        elif title.lower() in {
            "identity/evidence foundation",
            "lifecycle/fail-closed/done",
            "quiescence/oracle isolation",
            "scope/transition integrity",
            "provenance/cost/human accounting",
            "recovery/idempotency/concurrency",
            "real implementation audit",
            "e0 baseline",
            "e1 explicit acceptance pre-check / legitimate stop",
            "e1b matched deliberation",
            "host capability portability",
            "codex sandbox preflight",
        }:
            status = "IMPLEMENTED"
        elif title.lower() == "first real g0":
            status = "PAUSED"
        index += 1
        items.append(ExperimentalFront(index=index, title=title, status=status))
    return tuple(items)


def _parse_experimental_roadmap(root: Path) -> tuple[ExperimentalFront, ...]:
    roadmap = root / "docs" / "ROADMAP.md"
    items: list[ExperimentalFront] = []
    in_experimental = False
    index = 0
    for raw_line in roadmap.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.lower() == "## experimental ablation roadmap":
            in_experimental = True
            continue
        if not in_experimental:
            continue
        if not line or not line[0].isdigit():
            continue
        title = line.split(".", 1)[1].strip() if "." in line else line
        status = "OPEN"
        if title.lower() == "e0 baseline":
            status = "IMPLEMENTED"
        elif title.lower() == "e1 explicit acceptance pre-check / legitimate stop":
            status = "IMPLEMENTED"
        elif title.lower() == "e1b matched deliberation":
            status = "IMPLEMENTED"
        elif title.lower() == "e2 independent verifier":
            status = "IMPLEMENTED"
        index += 1
        items.append(ExperimentalFront(index=index, title=title, status=status))
    return tuple(items)


def build_e0_baseline_report(workspace: Path) -> E0BaselineReport:
    current_state = workspace / "docs" / "CURRENT-STATE.md"
    current_work = workspace / "docs" / "agent" / "CURRENT-WORK.md"
    engineering_roadmap = _parse_engineering_roadmap(workspace)
    experimental_roadmap = _parse_experimental_roadmap(workspace)
    paused_fronts = tuple(front for front in engineering_roadmap if front.title.lower() == "first real g0" and front.status == "PAUSED")
    next_open_front = next((front for front in experimental_roadmap if front.status == "OPEN"), None)
    head_match = re.search(r"^HEAD = `([^`]+)`", current_state.read_text(encoding="utf-8"), re.M)
    counters = {
        "REAL_CODEX_EXEC": 0,
        "REAL_CONTAINER_G0": 0,
        "REAL_A1": 0,
        "REAL_QUALIFIED_PAIRS": 0,
        "MEASURED_PRODUCT_EFFECT": "NO",
        "paused_g0_mentioned": "PAUSED / MUST RESUME" in current_work.read_text(encoding="utf-8"),
    }
    reasons = []
    if head_match is None:
        reasons.append("missing HEAD in current state")
    if not paused_fronts:
        reasons.append("missing paused first real G0 frontier")
    if next_open_front is None:
        reasons.append("missing next open experimental frontier")
    if next_open_front is not None and next_open_front.title != "E3 immutable submission + context evidence":
        reasons.append(f"unexpected next open frontier: {next_open_front.title}")
    return E0BaselineReport(
        workspace=str(workspace),
        current_state_head=head_match.group(1) if head_match is not None else "",
        scientific_counters=counters,
        paused_fronts=paused_fronts,
        next_open_front=next_open_front,
        baseline_ready=not reasons,
        baseline_reasons=tuple(reasons),
    )
