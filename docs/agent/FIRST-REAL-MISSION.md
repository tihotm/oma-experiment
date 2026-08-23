# First Real Mission

The first real mission for the MVP is the repository self-hosted `first real G0`.

Normative shape:

- workspace: the current repo checkout
- subject identity: current Git-backed subject at `HEAD`
- materialization identity: current repo materialization
- execution context identity: canonical runtime pins from `src/oma7/preflight.py`
- scope policy identity: canonical release-candidate scope policy
- verification context identity: canonical test-suite verification baseline
- mission identity: computed from the above pre-execution identities
- control policy identity: derived from the canonical retry budget
- harness binding identity: `oma7-harness:release-candidate`

Operational rule:

- the mission is derived before attempt creation
- `CODEX_AUTH_READY=False` must fail closed before any attempt is created
- once `CODEX_HOME` is authenticated, the same derived plan should be reusable without manual discovery of argv, mounts, or bindings

Read this together with:

- [CURRENT-WORK.md](CURRENT-WORK.md)
- [../ROADMAP.md](../ROADMAP.md)
- [../SPEC.md](../SPEC.md)
- [../LIFECYCLE.md](../LIFECYCLE.md)
