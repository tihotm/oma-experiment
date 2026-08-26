from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    required = (
        ROOT / "docs" / "ROADMAP.md",
        ROOT / "docs" / "CURRENT-STATE.md",
        ROOT / "docs" / "agent" / "CURRENT-WORK.md",
        ROOT / "src",
    )
    if not all(path.exists() for path in required):
        print("missing canonical docs or source", file=sys.stderr)
        return 1

    sys.path.insert(0, str(ROOT / "src"))
    from oma7.experimental_baseline import build_e0_baseline_report

    report = build_e0_baseline_report(ROOT)
    payload = report.as_dict()
    if args.json:
        print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    else:
        for key, value in payload.items():
            print(f"{key.upper()}={value}")
    return 0 if report.baseline_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
