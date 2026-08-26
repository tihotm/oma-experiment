# Current Work

Current factual state:

- The repo has a short AGENTS map plus an `docs/agent/INDEX.md` navigation entrypoint.
- `docs/` remains the system of record for SPEC, invariants, lifecycle, claims, and roadmap.
- The first real mission is the repository self-hosted `first real G0`, captured in `docs/agent/FIRST-REAL-MISSION.md`.
- The offline post-execution pipeline is represented by typed fixtures and ledger reconstruction tests.
- `src/oma7/accounting.py` now provides the canonical cost-ledger and human-intervention accounting primitives.
- `src/oma7/recovery.py` now classifies restart/replay outcomes over control, evidence, accounting, and post-execution persistence.
- `src/oma7/post_execution.py` now exposes a canonical artifact persistence helper that publishes evidence, writes accounting, and keeps the post-execution chain ledger-reconstructible.
- `src/oma7/release_candidate.py` now requires a factual `ReleaseCandidateExecutionCapture` payload before release-candidate evidence/accounting can be published, and synthetic `host_docker_e2e.py` success is explicitly blocked from product-evidence publication.
- `scripts/oma7-release-candidate-run.py` now reuses the canonical ephemeral `CODEX_HOME`, strips auxiliary `CODEX_API_KEY`/`OPENAI_API_KEY` from the execution environment, and consumes the canonical PowerShell host preflight probe result as the auth gate.
- `scripts/real-implementation-audit.py` now exposes a canonical implementation-audit report over the roadmap/current-state/claim-map docs.
- `scripts/oma7-e0-baseline.py` now exposes a canonical experimental baseline report that preserves the paused first-real-G0 lane and advances the next open experimental front to `E3 immutable submission + context evidence`.
- `scripts/oma7-e1-acceptance-precheck.py` now exposes a canonical acceptance-precheck report that preserves the paused first-real-G0 lane and advances the next open experimental front to `E3 immutable submission + context evidence`.
- `scripts/oma7-e1b-matched-deliberation.py` now exposes a canonical matched-deliberation report that preserves the paused first-real-G0 lane and advances the next open experimental front to `E3 immutable submission + context evidence`.
- `real implementation audit` has now been advanced in this runner and is mechanically discoverable from the canonical docs.
- `first real G0` remains `PAUSED / MUST RESUME` on the Windows interactive host boundary and must not be advanced in this runner.
- `src/oma7/codex_runtime.py` now separates Codex CLI availability from auth readiness in executable code.
- `src/oma7/host_portability.py` now resolves explicit Codex/Docker host capability selection without PATH being authoritative.
- Host Capability Provisioning is recorded as an external host boundary, not an OMA7 milestone.
- Host capability portability is now a documented roadmap milestone and is covered by fail-closed tests.
- Codex sandbox preflight is now implemented and documented; the current runner reports it as `ENVIRONMENT_BLOCKED`.
- `main` contains the integrated release-candidate merge `46cc437`.
- The interactive host reported `HOST_CAPABILITY_SUPPORT=SUPPORTED`, `CODEX_CLI_CAPABILITY=CLI_AVAILABLE`, `CODEX_AUTH_READY=True`, `ATTEMPT_CREATED=True`, `REAL_CODEX_EXEC=1`, and `MINIMAL_MISSION_RESULT=COMPLETED`.
- `python host_docker_e2e.py` executed 18 registered stages and all passed on the interactive host, including lifecycle, recovery, foreign-container isolation, verification reuse, idempotency, retry, Docker isolation, oracle isolation, repeatability, and cleanup.
- This runner's own verification suite now reports `Ran 212 tests in 202.663s | OK`.
- The historical first real attempt still lacks canonical persisted product evidence in the repo `evidence/` directory, so it remains unevaluable for G0 until the Windows interactive host produces a fresh eligible record.
- The canonical post-execution publication step now requires a factual real-execution capture payload; the already-completed historical run still has no persisted product evidence record in `evidence/`.
- The runner-side auth gate now reuses the canonical PowerShell host preflight probe result; the interactive host still needs live revalidation before the first real attempt can advance beyond auth.
- `real implementation audit` now has an executable report that marks the front as advanced in this runner, `scripts/oma7-e0-baseline.py` now identifies `E3 immutable submission + context evidence` as the next open experimental front, `scripts/oma7-e1-acceptance-precheck.py` now identifies `E3 immutable submission + context evidence` as the next open experimental front, and `scripts/oma7-e1b-matched-deliberation.py` now identifies `E3 immutable submission + context evidence` as the next open experimental front; `first real G0` remains paused / must resume on the Windows interactive host boundary.
- `REAL_CONTAINER_G0=0`, `REAL_A1=0`, `REAL_QUALIFIED_PAIRS=0`, and `MEASURED_PRODUCT_EFFECT=NO`.

Current blockers:

- The current checkout still lacks a persisted product execution evidence record suitable for canonical G0 evaluation from the historical attempt, and the paused `first real G0` lane must remain untouched until the Windows interactive host resumes it.

Current next action:

- Revalidate the canonical host preflight on the Windows interactive host so the newly wired persistence path can materialize fresh evidence/accounting from the next real execution, then evaluate the canonical G0 pipeline if the resulting record is eligible.
