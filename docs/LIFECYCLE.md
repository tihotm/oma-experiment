# Lifecycle Model

OMA7 uses an explicit supervisor-owned lifecycle. `DONE` is not executor-generated.

## States

- `PREPARED`
- `RUNNING`
- `EXECUTOR_TERMINATED`
- `QUIESCENCE_PENDING`
- `QUIESCENT`
- `FROZEN`
- `VERIFICATION_PENDING`
- `VERIFIED_PASS`
- `VERIFIED_FAIL`
- `EVIDENCE_PENDING`
- `EVAL_DONE`
- `RETRY_REQUIRED`
- `REVIEW_REQUIRED`
- `BLOCKED`
- `EXECUTION_FAILED`

## Acceptance boundary

`EVAL_DONE` is reachable only when:

- executor is not `RUNNING`
- quiescence is `PASS`
- freeze and integrity gates are `PASS`
- verifier result is `PASS`
- evidence uses the supported schema
- evidence is applicable to the current subject, materialization, execution,
  verification, scope, and provenance identities
- no mandatory acceptance-relevant identity is `UNKNOWN` or missing

## Legitimate no-op

`NO_OP` is a distinct acceptance outcome.

It requires:

- positive precheck that work is unnecessary
- current subject/materialization unchanged as expected
- applicable `PASS` evidence
- all mandatory gates `PASS`

## Retry and review

`RETRY_REQUIRED`, `REVIEW_REQUIRED`, and `BLOCKED` remain non-accepted until a
new material fact supports re-evaluation.

