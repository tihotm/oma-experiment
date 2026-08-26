from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def main(argv: list[str]) -> int:
    if not ((ROOT / "docs" / "ROADMAP.md").exists() and (ROOT / "docs" / "CURRENT-STATE.md").exists() and (ROOT / "docs" / "agent" / "CURRENT-WORK.md").exists()):
        print("missing canonical docs", file=sys.stderr)
        return 1
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from oma7.experimental_deliberation import build_e1b_matched_deliberation_report

    report = build_e1b_matched_deliberation_report(ROOT)
    payload = report.as_dict()
    if "--json" in argv:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"WORKSPACE={payload['workspace']}")
        print(f"MATCHED={payload['matched']}")
        print(f"PAUSED_FIRST_REAL_G0={payload['paused_first_real_g0']}")
        print(f"NEXT_OPEN_FRONT={payload['next_open_front']}")
        print(f"CONTRACT_READY={payload['contract_ready']}")
        print(f"MATCH_REASONS={list(payload['match_reasons'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
