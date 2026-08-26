from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RealImplementationAuditTests(unittest.TestCase):
    def test_audit_reports_paused_first_real_g0_and_next_front(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "real-implementation-audit.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["paused_fronts"])
        self.assertEqual(payload["paused_fronts"][0]["title"], "first real G0")
        self.assertIsNotNone(payload["next_pending_front"])
        self.assertEqual(payload["next_pending_front"]["title"], "E3 immutable submission + context evidence")

    def test_audit_fails_closed_when_required_docs_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            script = temp_root / "real-implementation-audit.py"
            script.write_text((ROOT / "scripts" / "real-implementation-audit.py").read_text(encoding="utf-8"), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=temp_root,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing canonical docs", result.stderr)


if __name__ == "__main__":
    unittest.main()
