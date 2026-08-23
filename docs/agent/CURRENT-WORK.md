# Current Work

Current factual state:

- The repo has a short AGENTS map plus an `docs/agent/INDEX.md` navigation entrypoint.
- `docs/` remains the system of record for SPEC, invariants, lifecycle, claims, and roadmap.
- The first real mission is the repository self-hosted `first real G0`, captured in `docs/agent/FIRST-REAL-MISSION.md`.
- The offline post-execution pipeline is represented by typed fixtures and ledger reconstruction tests.
- `src/oma7/accounting.py` now provides the canonical cost-ledger and human-intervention accounting primitives.
- `src/oma7/recovery.py` now classifies restart/replay outcomes over control, evidence, accounting, and post-execution persistence.
- Docker/runtime access is reachable from this session; the readiness script reports `DOCKER_RUNTIME_READY=True` and `PINNED_CODEX_RUNTIME_READY=True`.
- The current verified test baseline is `Ran 158 tests in 109.613s | OK (skipped=8)`.
- `main` contains the integrated release-candidate merge `46cc437`.
- `REAL_CODEX_EXEC=0`, `REAL_CONTAINER_G0=0`, `REAL_A1=0`, `REAL_QUALIFIED_PAIRS=0`, and `MEASURED_PRODUCT_EFFECT=NO`.

Current blockers:

- Codex authentication remains unperformed.

Current next action:

- Authenticate the same ephemeral `CODEX_HOME`, then proceed to the first real execution using the canonical readiness and production entrypoint.
