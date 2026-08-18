# Experiment P0

This experiment establishes the minimum reusable control-plane foundation for
OMA7.

## Rules

- Evidence-driven development only.
- Donor repositories are read-only.
- Prefer reuse, then composition, then adaptation, then build.
- Do not claim execution that was not run.

## Baseline contract

SWE-bench no-patch behavior is modeled by `skip_patch=True`, which suppresses
the effective model patch before evaluation.

## Identity model

- subject identity: Git-backed snapshot identity
- verification context: dataset revision + oracle/patch + test sets + harness
  commit + config + environment image
- evidence applicability: same subject + same context + PASS

