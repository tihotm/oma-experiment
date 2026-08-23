# Current Work

Current factual state:

- The repo has a short AGENTS map plus an `docs/agent/INDEX.md` navigation entrypoint.
- `docs/` remains the system of record for SPEC, invariants, lifecycle, claims, and roadmap.
- The offline post-execution pipeline is represented by typed fixtures and ledger reconstruction tests.
- Docker/runtime access is restored in this session; `docker context show` is `desktop-linux` and `docker info` succeeds.
- The current verified test baseline is `Ran 155 tests in 88.990s | OK`.
- `REAL_CODEX_EXEC=0`, `REAL_CONTAINER_G0=0`, `REAL_A1=0`, `REAL_QUALIFIED_PAIRS=0`, and `MEASURED_PRODUCT_EFFECT=NO`.

Current blockers:

- Codex authentication remains unperformed.

Current next action:

- Proceed to Codex login for the first real execution using the same ephemeral `CODEX_HOME` after any remaining human approval boundary.
