# OMA7 Specification

## Mission

OMA7 investigates and builds the control layer above existing coding agents.

Central scientific question:

Does a control layer above coding agents produce measurable advantage, and if so, what is its minimal powerful form?

## Normative order

### Scientific order

`TEST RESULT` -> `EMPIRICAL CLAIM` -> `INVARIANT` -> `EXISTING IMPLEMENTATIONS` -> `ONLY THEN ARCHITECTURE`

### Engineering order

`ADOPT` -> `COMPOSE` -> `ADAPT` -> `BUILD`

## Evidence hierarchy

- `DOCUMENTED`
- `CODE_CONFIRMED`
- `TEST_CONFIRMED`
- `EXECUTED`
- `MEASURED`

These levels MUST NOT be conflated.

`TEST_CONFIRMED` MUST NOT be treated as `EXECUTED`.

## Acceptance principles

- Agent completion != acceptance.
- Verifier PASS alone != sufficient acceptance.
- `UNKNOWN` != `PASS`.
- Acceptance evidence MUST bind required identities.
- Mutation makes incompatible evidence stale.
- DONE is evidence-derived.
- Human assistance MUST NOT be silently classified as autonomous.
- Cost-to-acceptance includes failed and retried trajectories.

## Normative requirements

OMA7 MUST preserve fail-closed acceptance boundaries.
OMA7 MUST prefer reusable primitives before custom construction.
OMA7 MUST NOT claim measured product advantage without real causal evidence.
OMA7 SHOULD keep architecture provisional until evidence justifies consolidation.
OMA7 MAY refine terminology as evidence evolves, but MUST record the change.

## Notes

This specification documents the current scientific and engineering contract.
It does not freeze the final architecture.

