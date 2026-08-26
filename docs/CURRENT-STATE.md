# Current State

Canonical invariant registry:

- [CANONICAL-INVARIANT-REGISTRY.md](CANONICAL-INVARIANT-REGISTRY.md)

HEAD = `8c870ca`

Scientific state:

REAL_CODEX_EXEC = 0
REAL_CONTAINER_G0 = 0
REAL_A1 = 0
REAL_QUALIFIED_PAIRS = 0
MEASURED_PRODUCT_EFFECT = NO

Current implementation status:

- `IMPLEMENTED`: Git-backed subject identity, materialization identity, execution context identity, verification context identity, scope policy identity, provenance anchor identity abstraction, expanded evidence model, canonical serialization, fail-closed schema parsing, explicit lifecycle state model, central acceptance gate, atomic evidence publication primitive, scope-control evaluation and acceptance composition, governance docs and policies, cost ledger primitives, human intervention accounting primitives, replay-safe append-only accounting/evidence persistence, stale-writer CAS guards, recovery classification helpers
- `PARTIAL`: provenance anchor composition, artifact/reference confusion boundary, false-DONE prevention, no-op acceptance boundary, some current-contract gaps from the audit
- `EXECUTED`: synthetic Docker lifecycle harness probes with real container execution, explicit cleanup, quiescence guard, freeze-after-quiescence path, an independent two-stage Docker verifier lifecycle, and synthetic supervision state/budget/recovery control-plane tests
- `MISSING`: real Codex execution, G0 measurement, external-effect idempotency, distributed supervision

Current canonical test command:

`python -m unittest discover -s tests -v`

Current discovered test count:

- before governance tests: 24
- after governance tests: 61

Runtime observations:

- current discovered test baseline is 191 cases across 18 `tests/test_*.py` modules
- offline control-plane coverage was expanded with `tests/test_control_plane_offline.py`
- `load_control_record` now preserves current attempt state on reload
- `tests/test_supervision_docker.py` now includes explicit runtime coverage for cross-run Docker isolation and oracle isolation across retries
- `scripts/oma7-release-candidate-readiness.py` derives the release-candidate rehearsal facts without manual transcription and now avoids recursive suite execution during readiness
- `scripts/oma7-e0-baseline.py` derives the canonical experimental baseline from docs and current state, preserves the paused first-real-G0 lane, and points the next open experimental front at `E3 immutable submission + context evidence`
- `scripts/oma7-e1-acceptance-precheck.py` derives the canonical acceptance-precheck report from docs and current state, preserves the paused first-real-G0 lane, and points the next open experimental front at `E3 immutable submission + context evidence`
- `scripts/oma7-e1b-matched-deliberation.py` derives the canonical matched-deliberation report from docs and current state, preserves the paused first-real-G0 lane, and points the next open experimental front at `E3 immutable submission + context evidence`
- `src/oma7/accounting.py` now provides the canonical cost-ledger and human-intervention record primitives used by provenance inputs and accounting summaries
- `src/oma7/recovery.py` now classifies persisted restart outcomes for control, evidence, accounting, and post-execution state
- `src/oma7/codex_runtime.py` now separates Codex CLI availability from auth readiness in executable code
- `src/oma7/release_candidate.py` now requires a factual `ReleaseCandidateExecutionCapture` payload before canonical product evidence/accounting can be persisted, and synthetic `host_docker_e2e.py` completion is explicitly blocked from product-evidence publication
- `src/oma7/host_portability.py` now resolves an explicit supported host context for Codex CLI and Docker without treating PATH discovery as authoritative
- Host Capability Provisioning is documented as an external boundary, not an OMA7 software milestone
- `src/oma7/preflight.py` now carries a canonical Codex sandbox preflight contract with typed command, mounts, workdir, network policy, ephemeral `CODEX_HOME`, and execution-plan identity
- `host_docker_e2e.py` is the host-native orchestrator for the pending Docker campaign, with explicit stage-to-scenario mapping
- restart recovery and persisted verification reuse are covered by unit and integration tests in `tests/test_supervision.py` and `tests/test_supervision_docker.py`
- multi-attempt Docker supervision and active-container recovery scenarios are encoded; this session now has Docker runtime access and Docker-dependent tests execute here
- the reproducible release candidate branch was merged back to `main` as `46cc437`
- production Docker execution should be exercised from an authorized host Python process context using the same `src/oma7/` code and the same `tests/`
- host capability portability is now represented as a documented milestone and is validated by explicit host-context selection tests
- Codex sandbox preflight is now documented and implemented; this runner reports it as `ENVIRONMENT_BLOCKED`
- CODEX auth remains pending; synthetic supervision is not G0

This file records factual state only.
