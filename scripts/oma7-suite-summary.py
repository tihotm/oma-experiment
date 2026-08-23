from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_suite() -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)


def _parse_summary(output: str) -> dict[str, object]:
    discovered = executed = skipped = failed = errors = None
    ran_match = re.search(r"^Ran\s+(\d+)\s+tests", output, re.M)
    skip_match = re.search(r"OK\s+\(skipped=(\d+)\)", output, re.M)
    summary_match = re.search(r"FAILED\s+\(failures=(\d+), errors=(\d+)\)", output, re.M)
    ok_match = re.search(r"^OK$", output, re.M)
    if ran_match:
        discovered = int(ran_match.group(1))
    if skip_match:
        skipped = int(skip_match.group(1))
    if summary_match:
        failed = int(summary_match.group(1))
        errors = int(summary_match.group(2))
    elif ok_match:
        failed = 0
        errors = 0
    if discovered is not None and skipped is not None:
        executed = discovered - skipped
    if executed is not None and failed is not None and errors is not None:
        succeeded = executed - failed - errors
    else:
        succeeded = None
    return {
        "tests_discovered": discovered,
        "tests_executed": executed,
        "tests_skipped": skipped,
        "tests_failed": (failed or 0) + (errors or 0),
        "tests_succeeded": succeeded,
        "raw_output": output,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rc, output = _run_suite()
    summary = _parse_summary(output)
    if args.json:
        print(json.dumps(summary, sort_keys=True, ensure_ascii=False))
    else:
        for key in ("tests_discovered", "tests_executed", "tests_skipped", "tests_failed", "tests_succeeded"):
            print(f"{key.upper()}={summary[key]}")
        print(summary["raw_output"])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
