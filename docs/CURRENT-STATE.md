# Current State

Canonical invariant registry:

- [CANONICAL-INVARIANT-REGISTRY.md](CANONICAL-INVARIANT-REGISTRY.md)

HEAD = `153b9c2832464ed0ec9ccf02ab4c7ec9e91f15d7`

Scientific state:

REAL_CODEX_EXEC = 0
REAL_CONTAINER_G0 = 0
REAL_A1 = 0
REAL_QUALIFIED_PAIRS = 0
MEASURED_PRODUCT_EFFECT = NO

Current implementation status:

- `IMPLEMENTED`: Git-backed subject identity, materialization identity, execution context identity, verification context identity, scope policy identity, provenance anchor identity abstraction, expanded evidence model, canonical serialization, fail-closed schema parsing, explicit lifecycle state model, central acceptance gate, atomic evidence publication primitive, scope-control evaluation and acceptance composition, governance docs and policies
- `PARTIAL`: provenance anchor composition, artifact/reference confusion boundary, false-DONE prevention, no-op acceptance boundary, some current-contract gaps from the audit
- `EXECUTED`: synthetic Docker lifecycle harness probes with real container execution, explicit cleanup, quiescence guard, freeze-after-quiescence path, an independent two-stage Docker verifier lifecycle, and synthetic supervision state/budget/recovery control-plane tests
- `MISSING`: real Codex execution, G0 measurement, cost ledger, human intervention accounting, concurrency lease/fencing/CAS, recovery engine, external-effect idempotency, distributed supervision

Current canonical test command:

`python -m unittest discover -s tests -v`

Current discovered test count:

- before governance tests: 24
- after governance tests: 61

Runtime observations:

- current discovered test baseline is 158 cases across 10 `tests/test_*.py` modules
- offline control-plane coverage was expanded with `tests/test_control_plane_offline.py`
- `load_control_record` now preserves current attempt state on reload
- `tests/test_supervision_docker.py` now includes explicit runtime coverage for cross-run Docker isolation and oracle isolation across retries
- `scripts/oma7-release-candidate-readiness.py` derives the release-candidate rehearsal facts without manual transcription
- `host_docker_e2e.py` is the host-native orchestrator for the pending Docker campaign, with explicit stage-to-scenario mapping
- restart recovery and persisted verification reuse are covered by unit and integration tests in `tests/test_supervision.py` and `tests/test_supervision_docker.py`
- multi-attempt Docker supervision and active-container recovery scenarios are encoded; this Codex sandbox token lacks Docker pipe authorization, while the host PowerShell user token can reach the Docker Desktop pipe
- production Docker execution should be exercised from an authorized host Python process context using the same `src/oma7/` code and the same `tests/`
- CODEX auth remains pending; synthetic supervision is not G0

This file records factual state only.
