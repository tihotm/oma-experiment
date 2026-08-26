# E2 Independent Verifier

Status: implemented by canonical independent verification reporting

## Purpose

`E2 independent verifier` independently replays the canonical baseline,
acceptance-precheck, and matched-deliberation reports and verifies that they
agree on the same next experimental frontier while preserving the paused
`first real G0` lane.

This front is independent of the Windows interactive host because it only
reuses canonical docs and production code that are already available in the
repository checkout.

## Contract

- The report MUST be derived from canonical repo docs and production code.
- The report MUST reuse the existing E0, E1, and E1b report builders.
- The report MUST confirm the three reports agree on the same next open front.
- The report MUST preserve `first real G0` as `PAUSED / MUST RESUME`.
- The report MUST fail closed if canonical docs are missing.
- The report MUST not claim real execution, G0, A1, or qualified-pair facts.

## Dependencies

- `docs/ROADMAP.md`
- `docs/CURRENT-STATE.md`
- `docs/agent/CURRENT-WORK.md`
- `docs/agent/E1B-MATCHED-DELIBERATION.md`
- `docs/agent/OPERATING-CONTRACT.md`
- `src/oma7/experimental_baseline.py`
- `src/oma7/experimental_acceptance.py`
- `src/oma7/experimental_deliberation.py`

## Acceptance

- `scripts/oma7-e2-independent-verifier.py` emits a canonical independent-verifier report.
- Baseline, acceptance-precheck, and matched-deliberation reports all agree.
- The report preserves the paused `first real G0` lane.
- The report identifies `E3 immutable submission + context evidence` as the next open experimental front.

