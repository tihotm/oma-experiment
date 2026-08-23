from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oma7.accounting import (
    AccountingEventKind,
    append_cost_entry,
    append_human_intervention,
    cost_ledger_event_count,
    cost_ledger_head,
    human_intervention_summary,
    load_accounting_ledger,
)
from oma7.scope import ProvenanceAnchorInputs, build_provenance_anchor
from oma7.models import (
    ExecutionContextIdentity,
    ScopePolicyIdentity,
    SubjectIdentity,
    VerificationContextIdentity,
)


class AccountingTests(unittest.TestCase):
    def _subject(self) -> SubjectIdentity:
        return SubjectIdentity(git_tree="tree", git_commit="commit", path=".")

    def _execution(self) -> ExecutionContextIdentity:
        return ExecutionContextIdentity(
            environment_container_image_digest="img",
            codex_binary_digest="codex",
            codex_version="0.1.0",
            model="model",
            reasoning_level="high",
            harness_commit_or_digest="harness",
            harness_configuration_digest="cfg",
            dependency_lock_digest="lock",
            dataset_revision="dataset",
            toolchain_identity="toolchain",
        )

    def _verification(self) -> VerificationContextIdentity:
        return VerificationContextIdentity(
            dataset_revision="dataset",
            oracle_test_patch_identity="oracle",
            fail_to_pass=(),
            pass_to_pass=(),
            harness_commit_or_digest="harness",
            verification_configuration_digest="verify",
            verifier_environment_image_digest="verifier",
            verifier_identity="verifier-1",
        )

    def _scope(self) -> ScopePolicyIdentity:
        return ScopePolicyIdentity(
            allowed_scope_path_policy=("src/**",),
            protected_semantic_roles=("oracle",),
            explicit_sensitive_change_authorizations=(),
            scope_budget="bounded",
            task_specific_exceptions=(),
            rule_schema_version="oma7.scope-policy/v1",
        )

    def test_cost_ledger_roundtrip_and_provenance_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            first = append_cost_entry("run-1", cost_units=3, reason="execution", base_dir=base)
            second = append_cost_entry("run-1", cost_units=2, kind=AccountingEventKind.VERIFICATION, reason="verification", base_dir=base)
            intervention = append_human_intervention(
                "run-1",
                human_actor="operator-1",
                reason="budget override review",
                approved=True,
                base_dir=base,
            )

            ledger = load_accounting_ledger("run-1", base)
            self.assertTrue(ledger.is_valid())
            self.assertEqual(ledger.event_count(), 3)
            self.assertEqual(cost_ledger_event_count("run-1", base), 3)
            self.assertEqual(len(ledger.entries), 2)
            self.assertEqual(len(ledger.human_interventions), 1)
            self.assertEqual(human_intervention_summary("run-1", base), "approved=1;blocked=0;total=1")
            self.assertEqual(first.event_index, 1)
            self.assertEqual(second.event_index, 2)
            self.assertEqual(intervention.event_index, 1)

            anchor = build_provenance_anchor(
                ProvenanceAnchorInputs(
                    subject_identity=self._subject(),
                    execution_context_identity=self._execution(),
                    verification_context_identity=self._verification(),
                    scope_policy_identity=self._scope(),
                    run_id="run-1",
                    verifier_id="verifier-1",
                    cost_ledger_head=cost_ledger_head("run-1", base),
                    cost_ledger_event_count=cost_ledger_event_count("run-1", base),
                    scope_change_id="change-1",
                )
            )
            self.assertTrue(anchor.identity.is_valid())
            self.assertEqual(anchor.identity.event_count, 3)

    def test_cost_ledger_fail_closed_on_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ledger_dir = base / "accounting"
            ledger_dir.mkdir(parents=True, exist_ok=True)
            path = ledger_dir / "run-1.jsonl"
            path.write_text('{"schema_version":"oma7.accounting/v1","run_id":"run-1","event_index":2,"kind":"EXECUTION","cost_units":1}\n', encoding="utf-8")
            self.assertEqual(cost_ledger_head("run-1", base), None)
            self.assertEqual(cost_ledger_event_count("run-1", base), 0)
            with self.assertRaises(ValueError):
                append_cost_entry("run-1", cost_units=1, base_dir=base)


if __name__ == "__main__":
    unittest.main()
