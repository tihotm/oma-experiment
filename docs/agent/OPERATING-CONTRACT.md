# Operating Contract

This is the canonical home for recurring agent-operating rules.
`AGENTS.md` only points here and to the navigation map.

## Authority order

Use this order when resolving a task:

1. normative documentation and invariants
2. guardrails and contracts
3. canonical types and schemas
4. existing code and call sites
5. tests
6. executed evidence
7. minimal local decision only when a real gap remains

## Autonomy

- Implement, test, correct, and integrate until the acceptance criterion or a real external blocker is reached.
- Do not stop at the first green test or the first fixed bug when more verified work remains.
- Prefer reuse, composition, and adaptation before building new structure.

## Evidence and state

- Keep `TEST_CONFIRMED`, `EXECUTED`, and `MEASURED` distinct.
- Update current factual state only with executed facts.
- Do not declare real execution, G0, A1, qualification, or product effect from fixtures or synthetic runs.

## Git and integration

- Default workflow: branch, commit, PR, CI, and merge.
- Direct `push` to `origin/main` is allowed only when a mission explicitly authorizes direct publication or when the repository workflow for that task says direct publication is the canonical path.
- Keep commits logical and evidence-backed.
- Do not commit or push unless the workflow or explicit request allows it.

## Boundaries and stopping

- Treat auth, Docker, and other external capabilities as boundaries, not success.
- A missing CLI is a capability boundary, not an auth state.
- `codex login status` is only meaningful after the Codex CLI is locatable by the supported host/runtime path.
- Continue on independent work when a partial blocker exists.
- Stop only at the first real external blocker that cannot be resolved in the repo or host session.

## Handoff

A normal task description may be:

- objective
- exceptional boundary, if any
- expected outcome / acceptance criterion

No repeated governance block is needed when this contract is reachable from `AGENTS.md`.
