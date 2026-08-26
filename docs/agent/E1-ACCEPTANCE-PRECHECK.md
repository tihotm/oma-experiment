# E1 Explicit Acceptance Pre-Check / Legitimate Stop

Status: implemented by canonical acceptance-precheck reporting

## Purpose

`E1 explicit acceptance pre-check / legitimate stop` exercises the existing
acceptance gate before any real execution, using a canonical no-op observation
that can resolve to a legitimate stop.

This front is independent of the Windows interactive host because it reuses
documented identities, lifecycle states, and the existing acceptance gate.

## Contract

- The pre-check MUST be derived from canonical repo docs and production code.
- The pre-check MUST use the existing acceptance gate in `src/oma7/lifecycle.py`.
- The pre-check MUST preserve `first real G0` as `PAUSED / MUST RESUME`.
- The pre-check MUST fail closed if canonical docs are missing.
- The pre-check MUST not claim real execution, G0, A1, or qualified-pair facts.

## Dependencies

- `docs/ROADMAP.md`
- `docs/CURRENT-STATE.md`
- `docs/agent/CURRENT-WORK.md`
- `docs/agent/E0-BASELINE.md`
- `docs/agent/OPERATING-CONTRACT.md`
- `src/oma7/lifecycle.py`
- `src/oma7/release_candidate.py`

## Acceptance

- `scripts/oma7-e1-acceptance-precheck.py` emits a canonical acceptance-precheck report.
- The report uses the existing acceptance gate and can report `NO_OP`.
- The report preserves the paused `first real G0` lane.
- The report identifies `E1b matched deliberation` as the next open experimental front.

