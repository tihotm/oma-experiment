# Execution Plans

This file records non-trivial lots and their evidence boundaries.

## Lot record template

- Objective
- Baseline HEAD
- Scope
- Excluded scope
- Relevant invariants
- Reuse candidates
- Expected evidence level
- Tests required
- Files changed
- Claims promoted
- Claims remaining open
- Final HEAD
- Repository status

## Current policy

Plans MUST not silently change the experimental roadmap.

If a lot discovers out-of-scope work, it MUST report it rather than implement it.

## Current lots

### Lot 2.5B

- Objective: freeze OMA7 governance and canonical knowledge in repository-owned artifacts
- Baseline HEAD: `4e94009`
- Scope: documentation, machine-readable policies, schemas, governance tests
- Excluded scope: runtime implementation, execution orchestration, multi-agent systems, custom skills
- Relevant invariants: governance/versioning, fail-closed acceptance, evidence-level separation
- Reuse candidates: current code/tests, current audit, existing docs
- Expected evidence level: `DOCUMENTED` and `TEST_CONFIRMED`
- Tests required: governance validation tests only
- Files changed: `AGENTS.md`, `PLANS.md`, `docs/*`, `policies/*`, `schemas/*`, tests
- Claims promoted: none yet
- Claims remaining open: runtime implementation and execution lots
- Final HEAD: pending
- Repository status: pending

