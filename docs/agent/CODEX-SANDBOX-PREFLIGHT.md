# Codex Sandbox Preflight

## Objective

Provide a fail-closed, reproducible preflight for the Codex sandbox boundary
used by OMA7 production readiness.

The sandbox preflight must validate the derived execution environment without
performing a real Codex model call.

## Scope

This milestone covers the derived sandbox boundary for the first real mission:

- workspace
- runtime pins
- execution context identity
- ephemeral `CODEX_HOME`
- command construction
- mount construction
- workdir
- network / egress policy
- readiness integration

It does not cover:

- authentication
- real Codex execution
- G0 measurement
- attempt creation
- host provisioning

## Normative basis

The first real mission already requires that, once auth becomes available, the
same derived plan can be reused without manual discovery of argv, mounts, or
bindings.

This milestone makes the sandbox side of that requirement explicit and
machine-checkable.

## Invariants

- Sandbox preflight MUST be derived from canonical types and runtime pins.
- `CODEX_HOME` MUST be explicit or reproducibly derived from the host session.
- Command, mounts, workdir, and network policy MUST be represented as typed
  facts.
- Network policy MUST fail closed when the sandbox is not isolated as expected.
- Missing or malformed sandbox facts MUST block readiness.
- The sandbox contract MUST remain distinct from auth and real execution.

## Interfaces affected

- `src/oma7/preflight.py`
- `src/oma7/release_candidate.py`
- `scripts/oma7-release-candidate-readiness.py`
- `scripts/host-codex-preflight.ps1`
- `tests/test_release_candidate.py`
- `tests/test_oma7_core.py`

## Acceptance criteria

- Sandbox preflight returns a typed result containing:
  - execution context identity
  - `CODEX_HOME`
  - command
  - mounts
  - workdir
  - network policy
- Readiness emits the sandbox preflight result facts.
- Tests prove the sandbox preflight is fail-closed when command, mounts, or
  network policy are invalid.
- Tests prove the sandbox result is reproducible from the canonical first
  mission inputs.

## Architectural limits

- No new real execution path is introduced.
- No auth material is copied or synthesized.
- No real model call or G0 execution is performed.

