# Current Work

Current factual state:

- The repo has a short AGENTS map plus an `docs/agent/INDEX.md` navigation entrypoint.
- `docs/` remains the system of record for SPEC, invariants, lifecycle, claims, and roadmap.
- The first real mission is the repository self-hosted `first real G0`, captured in `docs/agent/FIRST-REAL-MISSION.md`.
- The offline post-execution pipeline is represented by typed fixtures and ledger reconstruction tests.
- `src/oma7/accounting.py` now provides the canonical cost-ledger and human-intervention accounting primitives.
- `src/oma7/recovery.py` now classifies restart/replay outcomes over control, evidence, accounting, and post-execution persistence.
- `src/oma7/codex_runtime.py` now separates Codex CLI availability from auth readiness in executable code.
- `src/oma7/host_portability.py` now resolves explicit Codex/Docker host capability selection without PATH being authoritative.
- Host Capability Provisioning is recorded as an external host boundary, not an OMA7 milestone.
- Docker/runtime access is capability-blocked in this runner; the readiness script reports `DOCKER_RUNTIME_READY=False` and `PINNED_CODEX_RUNTIME_READY=False`.
- The current verified test baseline is `Ran 169 tests in 207.754s | OK (skipped=8)`.
- In this runner, `codex` is not locatable via `where.exe`; that is a capability boundary, not auth state.
- Host capability portability is now a documented roadmap milestone and is covered by fail-closed tests.
- Codex sandbox preflight is now implemented and documented; the current runner reports it as `ENVIRONMENT_BLOCKED`.
- `main` contains the integrated release-candidate merge `46cc437`.
- `REAL_CODEX_EXEC=0`, `REAL_CONTAINER_G0=0`, `REAL_A1=0`, `REAL_QUALIFIED_PAIRS=0`, and `MEASURED_PRODUCT_EFFECT=NO`.

Current blockers:

- Codex authentication remains unperformed.

Current next action:

- Authenticate the same ephemeral `CODEX_HOME`, then proceed to the first real execution using the canonical readiness and production entrypoint.
