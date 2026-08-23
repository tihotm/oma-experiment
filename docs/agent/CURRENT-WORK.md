# Current Work

Current factual state:

- The repo has a short AGENTS map plus an `docs/agent/INDEX.md` navigation entrypoint.
- `docs/` remains the system of record for SPEC, invariants, lifecycle, claims, and roadmap.
- The first real mission is the repository self-hosted `first real G0`, captured in `docs/agent/FIRST-REAL-MISSION.md`.
- The offline post-execution pipeline is represented by typed fixtures and ledger reconstruction tests.
- Docker/runtime access is not currently reachable from this session; the readiness script reports `DOCKER_RUNTIME_READY=False` and the Docker-dependent tests remain skipped here.
- The current verified test baseline is `Ran 151 tests in 33.897s | OK (skipped=8)`.
- `REAL_CODEX_EXEC=0`, `REAL_CONTAINER_G0=0`, `REAL_A1=0`, `REAL_QUALIFIED_PAIRS=0`, and `MEASURED_PRODUCT_EFFECT=NO`.

Current blockers:

- Codex authentication remains unperformed.

Current next action:

- Restore Docker/runtime access from an authorized host context, then proceed to Codex login for the first real execution using the same ephemeral `CODEX_HOME`.
