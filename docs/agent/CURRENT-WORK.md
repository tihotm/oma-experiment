# Current Work

Current factual state:

- The repo has a short AGENTS map plus an `docs/agent/INDEX.md` navigation entrypoint.
- `docs/` remains the system of record for SPEC, invariants, lifecycle, claims, and roadmap.
- The offline post-execution pipeline is represented by typed fixtures and ledger reconstruction tests.
- Runtime and Docker access remain externally blocked in this session; `docker info` still fails on `npipe:////./pipe/docker_engine`.
- The current verified test baseline is `Ran 155 tests in 92.494s | OK`.
- `REAL_CODEX_EXEC=0`, `REAL_CONTAINER_G0=0`, `REAL_A1=0`, `REAL_QUALIFIED_PAIRS=0`, and `MEASURED_PRODUCT_EFFECT=NO`.

Current blockers:

- Docker daemon access denied for the current process token.
- Codex authentication remains unperformed.

Current next action:

- Restore Docker/runtime access, rerun `scripts/host-codex-preflight.ps1`, then proceed to Codex login for the first real execution.
