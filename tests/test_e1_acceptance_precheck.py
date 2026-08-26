from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class E1AcceptancePrecheckTests(unittest.TestCase):
    def test_e1_precheck_reports_legitimate_stop_and_preserves_paused_g0(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "oma7-e1-acceptance-precheck.py"), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["contract_ready"])
        self.assertTrue(payload["paused_first_real_g0"])
        self.assertEqual(payload["next_open_front"], "E3 immutable submission + context evidence")
        self.assertEqual(payload["acceptance"]["outcome"], "NO_OP")
        self.assertEqual(payload["acceptance"]["lifecycle_state"], "EVAL_DONE")
        self.assertEqual(payload["acceptance"]["reason"], "legitimate no-op accepted")
        self.assertTrue(payload["baseline_no_op_ready"])

    def test_e1_precheck_fails_closed_when_required_docs_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            script_dir = temp_root / "scripts"
            script_dir.mkdir(parents=True, exist_ok=True)
            script = script_dir / "oma7-e1-acceptance-precheck.py"
            script.write_text((ROOT / "scripts" / "oma7-e1-acceptance-precheck.py").read_text(encoding="utf-8"), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=temp_root,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing canonical docs or source", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
