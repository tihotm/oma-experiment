# Roadmap

## Engineering roadmap

1. Governance freeze
1. Identity/evidence foundation
1. Lifecycle/fail-closed/DONE
1. Quiescence/oracle isolation
1. Scope/transition integrity
1. Provenance/cost/human accounting
1. Recovery/idempotency/concurrency
1. real implementation audit
1. Host capability portability
1. Codex sandbox preflight
1. first real G0

Host capability portability covers explicit selection and validation of a
supported host context for Codex CLI and Docker capability without depending on
PATH discovery as authoritative state.

Identity/evidence foundation is complete only to the extent supported by current code/tests at HEAD `8130ac1`.

## Experimental ablation roadmap

1. E0 baseline
1. E1 explicit acceptance pre-check / legitimate stop
1. E1b matched deliberation
1. E2 independent verifier
1. E3 immutable submission + context evidence
1. E4 recovery
1. E5 selective retry
1. E6 cost-aware controller
1. E7 targeted scouting
1. E8 conditional multi-agent

Engineering availability does not justify causal experimental promotion.

E0 baseline is implemented by the canonical experimental baseline report in
`scripts/oma7-e0-baseline.py` and its supporting tests. E1 explicit acceptance
pre-check / legitimate stop is implemented by the canonical acceptance-precheck
report in `scripts/oma7-e1-acceptance-precheck.py` and its supporting tests.
E1b matched deliberation is implemented by the canonical matched-deliberation
report in `scripts/oma7-e1b-matched-deliberation.py` and its supporting tests.
E2 independent verifier is implemented by the canonical independent-verifier
report in `scripts/oma7-e2-independent-verifier.py` and its supporting tests.
The next open experimental front is `E3 immutable submission + context evidence`.

## SKILL CANDIDATES

- lot audit - `DEFERRED_PENDING_WORKFLOW_STABILITY`
- experiment execution - `DEFERRED_PENDING_WORKFLOW_STABILITY`
- evidence verification - `DEFERRED_PENDING_WORKFLOW_STABILITY`
- lot closure - `DEFERRED_PENDING_WORKFLOW_STABILITY`
