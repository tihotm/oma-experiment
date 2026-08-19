# Current State

HEAD = `1398771a77f0a8f98467b9b49063c9536d5034b3`

Scientific state:

REAL_CODEX_EXEC = 0
REAL_CONTAINER_G0 = 0
REAL_A1 = 0
REAL_QUALIFIED_PAIRS = 0
MEASURED_PRODUCT_EFFECT = NO

Current implementation status:

- `IMPLEMENTED`: Git-backed subject identity, materialization identity, execution context identity, verification context identity, scope policy identity, provenance anchor identity abstraction, expanded evidence model, canonical serialization, fail-closed schema parsing, explicit lifecycle state model, central acceptance gate, atomic evidence publication primitive, governance docs and policies
- `PARTIAL`: provenance anchor composition, artifact/reference confusion boundary, false-DONE prevention, no-op acceptance boundary, some current-contract gaps from the audit
- `MISSING`: executor quiescence runtime, oracle temporal isolation, cost ledger, human intervention accounting, concurrency lease/fencing/CAS, recovery engine, external-effect idempotency, distributed supervision

Current canonical test command:

`python -m unittest discover -s tests -v`

Current discovered test count:

- before governance tests: 24
- after governance tests: 61

This file records factual state only.
