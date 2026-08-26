# E0 Baseline

Status: implemented by canonical baseline reporting

## Purpose

`E0 baseline` establishes a machine-readable scientific baseline for the
experimental roadmap without performing a real OMA7 execution.

The baseline reuses the already-implemented release-candidate and current-state
primitives to report:

- the current repository state head
- the documented zero-valued scientific counters
- the paused `first real G0` boundary
- the next open experimental front after the baseline

## Contract

- The baseline MUST be derived from canonical repo docs and production code.
- The baseline MUST NOT fabricate real execution, G0, A1, or qualified-pair
  evidence.
- The baseline MUST preserve `first real G0` as `PAUSED / MUST RESUME`.
- The baseline MUST be fail-closed when canonical docs are missing.
- The baseline MUST remain reproducible from the current repository state.

## Dependencies

- `docs/ROADMAP.md`
- `docs/CURRENT-STATE.md`
- `docs/agent/CURRENT-WORK.md`
- `docs/agent/OPERATING-CONTRACT.md`
- `src/oma7/release_candidate.py`
- `docs/agent/FIRST-REAL-MISSION.md`

## Acceptance

- `scripts/oma7-e0-baseline.py` emits a canonical baseline report.
- The report preserves the paused `first real G0` lane.
- The report identifies `E1 explicit acceptance pre-check / legitimate stop`
  as the next open experimental front.
- The report does not mutate scientific counters or claim real execution.

