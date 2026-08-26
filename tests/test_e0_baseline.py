from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class E0BaselineTests(unittest.TestCase):
    def test_e0_baseline_reports_paused_first_real_g0_and_next_front(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "oma7-e0-baseline.py"), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["baseline_ready"])
        self.assertTrue(payload["paused_fronts"])
        self.assertEqual(payload["paused_fronts"][0]["title"], "first real G0")
        self.assertIsNotNone(payload["next_open_front"])
        self.assertEqual(payload["next_open_front"]["title"], "E3 immutable submission + context evidence")
        self.assertEqual(payload["scientific_counters"]["REAL_CODEX_EXEC"], 0)
        self.assertEqual(payload["scientific_counters"]["REAL_CONTAINER_G0"], 0)
        self.assertEqual(payload["scientific_counters"]["REAL_A1"], 0)
        self.assertEqual(payload["scientific_counters"]["REAL_QUALIFIED_PAIRS"], 0)
        self.assertEqual(payload["scientific_counters"]["MEASURED_PRODUCT_EFFECT"], "NO")
        self.assertTrue(payload["scientific_counters"]["paused_g0_mentioned"])

    def test_e0_baseline_fails_closed_when_required_docs_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            script = temp_root / "oma7-e0-baseline.py"
            script.write_text((ROOT / "scripts" / "oma7-e0-baseline.py").read_text(encoding="utf-8"), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=temp_root,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing", result.stderr.lower() or result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
