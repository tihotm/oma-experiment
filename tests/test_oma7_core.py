from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oma7.git_identity import compute_git_tree_identity
from oma7.models import Evidence, ResultStatus, SubjectIdentity, VerificationContextIdentity
from oma7.qualifier import qualify_observation
from oma7.snapshot import freeze_snapshot
from oma7.swebench_adapter import normalize_b0_observation
from oma7.swebench_contract import effective_model_patch
from oma7.verifier import verify_evidence, verify_snapshot_is_copy


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(["git", *cmd], cwd=cwd, check=True, capture_output=True, text=True)


class Oma7CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        _git(["init"], self.repo)
        _git(["config", "user.email", "test@example.com"], self.repo)
        _git(["config", "user.name", "Test User"], self.repo)
        (self.repo / "tracked.txt").write_text("one\n", encoding="utf-8")
        _git(["add", "tracked.txt"], self.repo)
        _git(["commit", "-m", "init"], self.repo)

    def _identity(self):
        return SubjectIdentity(git_tree="tree", git_commit="commit", path=".")

    def _context(self, dataset_revision="rev1", environment_image="img"):
        return VerificationContextIdentity(
            dataset_revision=dataset_revision,
            test_patch_oracle="oracle",
            fail_to_pass=("a",),
            pass_to_pass=("b",),
            harness_commit="h1",
            verification_config="cfg",
            environment_image=environment_image,
        )

    def test_git_identity_changes_on_content_mutation(self) -> None:
        base = compute_git_tree_identity(self.repo)
        (self.repo / "tracked.txt").write_text("two\n", encoding="utf-8")
        changed = compute_git_tree_identity(self.repo)
        self.assertNotEqual(base, changed)

    def test_snapshot_is_copy_and_stable(self) -> None:
        snapshot, frozen_dir = freeze_snapshot(self.repo)
        self.assertTrue(verify_snapshot_is_copy(frozen_dir, self.repo))
        before = snapshot
        (self.repo / "tracked.txt").write_text("mutated\n", encoding="utf-8")
        after, _ = freeze_snapshot(self.repo)
        self.assertNotEqual(before, after)

    def test_same_subject_context_accepts(self) -> None:
        subject = self._identity()
        context = self._context()
        evidence = Evidence(subject, context, ResultStatus.PASS)
        applicability = verify_evidence(evidence, subject, context, ResultStatus.PASS)
        self.assertTrue(applicability.authorizes_acceptance)

    def test_mutation_rejects(self) -> None:
        subject = self._identity()
        context = self._context()
        evidence = Evidence(subject, context, ResultStatus.PASS)
        cases = [
            ("source mutation", SubjectIdentity(git_tree="other", git_commit="commit", path="."), context),
            ("test/oracle mutation", subject, self._context(dataset_revision="rev1", environment_image="img2")),
            ("verification config mutation", subject, VerificationContextIdentity("rev1", "oracle", ("a",), ("b",), "h1", "cfg2", "img")),
            ("dependency manifest mutation", subject, self._context(environment_image="img-deps")),
            ("lockfile mutation", subject, self._context(dataset_revision="rev-lock")),
            ("deletion mutation", SubjectIdentity(git_tree="deleted", git_commit="commit", path="."), context),
            ("rename mutation", SubjectIdentity(git_tree="renamed", git_commit="commit", path="."), context),
            ("harness version mutation", subject, VerificationContextIdentity("rev1", "oracle", ("a",), ("b",), "h2", "cfg", "img")),
            ("dataset revision mutation", subject, self._context(dataset_revision="rev2")),
            ("environment identity mutation", subject, self._context(environment_image="img2")),
        ]
        for name, mutated_subject, mutated_context in cases:
            with self.subTest(name=name):
                applicability = verify_evidence(
                    evidence, mutated_subject, mutated_context, ResultStatus.PASS
                )
                self.assertFalse(applicability.authorizes_acceptance)

    def test_fail_evidence_never_authorizes_acceptance(self) -> None:
        subject = self._identity()
        context = self._context()
        evidence = Evidence(subject, context, ResultStatus.FAIL)
        applicability = verify_evidence(evidence, subject, context, ResultStatus.FAIL)
        self.assertFalse(applicability.authorizes_acceptance)

    def test_skip_patch_ignores_prediction_patch(self) -> None:
        self.assertEqual(effective_model_patch({"model_patch": "diff --git a b"}, skip_patch=True), "")
        self.assertEqual(
            effective_model_patch({"model_patch": "diff --git a b"}, skip_patch=False),
            "diff --git a b",
        )

    def test_normalizer_and_qualifier(self) -> None:
        subject = self._identity()
        context = self._context()
        obs = normalize_b0_observation(
            {
                "subject_identity": subject,
                "verification_context_identity": context,
                "result": "PASS",
                "tests_status": {"test_a": "FAIL"},
            }
        )
        self.assertEqual(obs.result, ResultStatus.PASS)
        self.assertEqual(qualify_observation(obs).value, "QUALIFIED")


if __name__ == "__main__":
    unittest.main()
