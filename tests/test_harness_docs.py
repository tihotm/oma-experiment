from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HarnessDocsTests(unittest.TestCase):
    def test_harness_validation_script_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate-harness.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("harness validation ok", result.stdout)

    def test_agents_points_to_navigation_and_state(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("docs/agent/INDEX.md", agents)
        self.assertIn("docs/agent/CURRENT-WORK.md", agents)
        self.assertIn("`docs/` is the system of record.", agents)
        self.assertIn("docs/agent/OPERATING-CONTRACT.md", agents)
        self.assertIn("docs/SPEC.md", agents)
        self.assertIn("docs/INVARIANTS.md", agents)
        self.assertIn("docs/CURRENT-STATE.md", agents)
        self.assertIn("docs/ROADMAP.md", agents)

    def test_operating_contract_contains_recurring_governance(self) -> None:
        contract = (ROOT / "docs" / "agent" / "OPERATING-CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("Authority order", contract)
        self.assertIn("Autonomy", contract)
        self.assertIn("Evidence and state", contract)
        self.assertIn("Git and integration", contract)
        self.assertIn("Default workflow: branch, commit, PR, CI, and merge.", contract)
        self.assertIn("Direct `push` to `origin/main` is allowed only when", contract)
        self.assertIn("Boundaries and stopping", contract)
        self.assertIn("A missing CLI is a capability boundary, not an auth state.", contract)
        self.assertIn("`codex login status` is only meaningful after the Codex CLI is locatable", contract)
        self.assertIn("Handoff", contract)


if __name__ == "__main__":
    unittest.main()
