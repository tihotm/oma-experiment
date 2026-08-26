from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from oma7.experimental_verifier import build_e2_independent_verifier_report


class E2IndependentVerifierTests(TestCase):
    def test_e2_reports_matched_reports_and_preserves_paused_g0(self) -> None:
        payload = build_e2_independent_verifier_report(ROOT).as_dict()
        self.assertEqual(payload["workspace"], str(ROOT))
        self.assertTrue(payload["matched"])
        self.assertTrue(payload["paused_first_real_g0"])
        self.assertEqual(payload["next_open_front"], "E3 immutable submission + context evidence")
        self.assertTrue(payload["contract_ready"])
        self.assertEqual(payload["baseline_next_front"], "E3 immutable submission + context evidence")
        self.assertEqual(payload["acceptance_next_front"], "E3 immutable submission + context evidence")
        self.assertEqual(payload["deliberation_next_front"], "E3 immutable submission + context evidence")

    def test_e2_fails_closed_when_required_docs_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            (temp_root / "docs" / "agent").mkdir(parents=True, exist_ok=True)
            (temp_root / "src" / "oma7").mkdir(parents=True, exist_ok=True)
            (temp_root / "scripts").mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "scripts" / "oma7-e2-independent-verifier.py", temp_root / "scripts" / "oma7-e2-independent-verifier.py")
            proc = subprocess.run(
                [sys.executable, str(temp_root / "scripts" / "oma7-e2-independent-verifier.py")],
                cwd=temp_root,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("missing canonical docs", proc.stderr)
