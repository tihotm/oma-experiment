# Evidence Model

OMA7 evidence is an expanded immutable binding over:

- `subject_identity`
- `materialization_identity`
- `execution_context_identity`
- `verification_context_identity`
- `scope_policy_identity`
- `provenance_anchor_identity`
- `result`
- `schema_version`

## Applicability rule

Evidence is applicable only when:

- `result == PASS`
- subject identity matches exactly
- materialization identity matches exactly
- execution context identity matches exactly
- verification context identity matches exactly
- scope policy identity matches exactly
- provenance anchor identity matches exactly

Missing or unknown required identities are not applicable.

## Schema handling

- supported schema parses normally
- missing mandatory schema is invalid
- unsupported future schema is invalid / not applicable
- unknown enum/value in an acceptance-relevant field is invalid / not applicable

## Canonical serialization

Identity hashing uses deterministic canonical serialization.
Dictionary ordering differences must not change identity.
Unsupported or noncanonical values fail closed instead of being silently
stringified.

## Forward-compatible fields

Reserved for later composition:

- `verifier_id`
- `run_id`
- `cost_ledger_head`
- `cost_ledger_event_count`
- `human_intervention_summary`

