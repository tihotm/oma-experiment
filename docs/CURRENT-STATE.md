# Current State

HEAD = `4e94009`

Scientific state:

REAL_CODEX_EXEC = 0
REAL_CONTAINER_G0 = 0
REAL_A1 = 0
REAL_QUALIFIED_PAIRS = 0
MEASURED_PRODUCT_EFFECT = NO

Current implementation status:

- `IMPLEMENTED`: Git-backed subject identity, materialization identity, execution context identity, verification context identity, scope policy identity, provenance anchor identity abstraction, expanded evidence model, canonical serialization, fail-closed schema parsing, governance docs and policies
- `PARTIAL`: provenance anchor composition, artifact/reference confusion boundary, false-DONE boundary, some current-contract gaps from the audit
- `MISSING`: executor quiescence, oracle temporal isolation, atomic publication, cost ledger, human intervention accounting, concurrency lease/fencing/CAS, recovery engine, external-effect idempotency

Current canonical test command:

`python -m unittest discover -s tests -v`

Current discovered test count:

- before governance tests: 15
- after governance tests: 23

This file records factual state only.
