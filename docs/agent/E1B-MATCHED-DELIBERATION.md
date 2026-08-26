# E1b Matched Deliberation

Status: implemented by canonical matched-deliberation reporting

## Purpose

`E1b matched deliberation` exercises the same canonical acceptance-precheck
lane twice and requires both deliberations to agree on the legitimate no-op
stop.

This front remains independent of the Windows interactive host because it only
reuses canonical docs, the existing acceptance gate, and the deterministic
mission/capability bindings already available in production code.

## Contract

- The report MUST be derived from canonical repo docs and production code.
- The report MUST use the existing acceptance gate in `src/oma7/lifecycle.py`.
- The report MUST build two independent canonical deliberations from the same
  workspace inputs.
- The report MUST preserve `first real G0` as `PAUSED / MUST RESUME`.
- The report MUST fail closed if canonical docs are missing.
- The report MUST not claim real execution, G0, A1, or qualified-pair facts.
- The report MUST treat a matched legitimate no-op stop as the expected result.

## Dependencies

- `docs/ROADMAP.md`
- `docs/CURRENT-STATE.md`
- `docs/agent/CURRENT-WORK.md`
- `docs/agent/E1-ACCEPTANCE-PRECHECK.md`
- `docs/agent/OPERATING-CONTRACT.md`
- `src/oma7/lifecycle.py`
- `src/oma7/release_candidate.py`

## Acceptance

- `scripts/oma7-e1b-matched-deliberation.py` emits a canonical matched-deliberation report.
- Both deliberations resolve to the same legitimate no-op acceptance outcome.
- The report preserves the paused `first real G0` lane.
- The report identifies `E2 independent verifier` as the next open experimental front.

