from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs" / "ROADMAP.md"
CURRENT_STATE = ROOT / "docs" / "CURRENT-STATE.md"
CURRENT_WORK = ROOT / "docs" / "agent" / "CURRENT-WORK.md"
CLAIM_MAP = ROOT / "docs" / "CLAIM-MAP.md"


@dataclass(frozen=True)
class RoadmapItem:
    index: int
    title: str
    status: str


def _parse_roadmap() -> list[RoadmapItem]:
    items: list[RoadmapItem] = []
    in_engineering = False
    index = 0
    for raw_line in ROADMAP.read_text(encoding="utf-8").splitlines():
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
            "e2 independent verifier",
            "host capability portability",
            "codex sandbox preflight",
        }:
            status = "IMPLEMENTED"
        elif title.lower() == "first real g0":
            status = "PAUSED"
        index += 1
        items.append(RoadmapItem(index=index, title=title, status=status))
    return items


def _pick_next_front(items: list[RoadmapItem]) -> RoadmapItem | None:
    for item in items:
        if item.status == "OPEN" and item.title.lower() != "first real g0":
            return item
    return None


def main() -> int:
    if not (ROADMAP.exists() and CURRENT_STATE.exists() and CURRENT_WORK.exists() and CLAIM_MAP.exists()):
        print("missing canonical docs", file=sys.stderr)
        return 1

    items = _parse_roadmap()
    next_front = _pick_next_front(items)
    payload = {
        "roadmap": [item.__dict__ for item in items],
        "next_pending_front": None if next_front is None else next_front.__dict__,
        "paused_fronts": [item.__dict__ for item in items if item.status == "PAUSED"],
        "current_state_head": re.search(r"^HEAD = `([^`]+)`", CURRENT_STATE.read_text(encoding="utf-8"), re.M).group(1),
        "current_work_mentions_paused_g0": "PAUSED / MUST RESUME" in CURRENT_WORK.read_text(encoding="utf-8"),
        "claim_map_entries": len([line for line in CLAIM_MAP.read_text(encoding="utf-8").splitlines() if line.startswith("- ") or line.startswith("- `")]),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
