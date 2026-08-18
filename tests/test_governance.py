from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _load_json(path: str):
    return json.loads(_read(path))


class GovernanceTests(unittest.TestCase):
    def test_experiment_policy_cannot_classify_test_confirmed_as_executed(self) -> None:
        policy = _load_json("policies/experiment-policy.yaml")
        self.assertFalse(policy["promotion_rules"]["TEST_CONFIRMED_to_EXECUTED"])

    def test_real_execution_counters_remain_zero(self) -> None:
        policy = _load_json("policies/experiment-policy.yaml")
        counters = policy["real_execution_counters"]
        self.assertEqual(counters["REAL_CODEX_EXEC"], 0)
        self.assertEqual(counters["REAL_CONTAINER_G0"], 0)
        self.assertEqual(counters["REAL_A1"], 0)
        self.assertEqual(counters["REAL_QUALIFIED_PAIRS"], 0)

    def test_required_evidence_identities_cannot_be_omitted(self) -> None:
        schema = _load_json("schemas/evidence.schema.json")
        self.assertCountEqual(
            schema["required"],
            [
                "schema_version",
                "subject_identity",
                "materialization_identity",
                "execution_context_identity",
                "verification_context_identity",
                "scope_policy_identity",
                "provenance_anchor_identity",
                "result",
            ],
        )

    def test_unsupported_evidence_schema_fails_closed(self) -> None:
        schema = _load_json("schemas/evidence.schema.json")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "oma7.evidence/v1")

    def test_invalid_policy_enum_value_is_constrained(self) -> None:
        policy_schema = _load_json("schemas/policy.schema.json")
        self.assertIn("NO", policy_schema["properties"]["measured_product_effect"]["enum"])
        self.assertIn("YES", policy_schema["properties"]["measured_product_effect"]["enum"])

    def test_agents_references_canonical_docs(self) -> None:
        agents = _read("AGENTS.md")
        self.assertIn("docs/SPEC.md", agents)
        self.assertIn("docs/INVARIANTS.md", agents)
        self.assertIn("docs/CURRENT-STATE.md", agents)
        self.assertIn("docs/ROADMAP.md", agents)

    def test_current_state_counters_agree_with_policy(self) -> None:
        current_state = _read("docs/CURRENT-STATE.md")
        policy = _load_json("policies/experiment-policy.yaml")
        for key, value in policy["real_execution_counters"].items():
            self.assertIn(f"{key} = {value}", current_state)

    def test_invariant_ids_are_unique_and_gap_free(self) -> None:
        text = _read("docs/INVARIANTS.md")
        ids = [int(match.group(1)) for match in re.finditer(r"^I(\d+)$", text, re.M)]
        self.assertEqual(ids, list(range(1, 75)))
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
