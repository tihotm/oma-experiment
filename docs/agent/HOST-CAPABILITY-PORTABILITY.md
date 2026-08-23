# Host Capability Portability

## Objective

Detect and validate a host context that can support OMA7 production readiness
without depending on accidental PATH discovery or on implicit token/process
context.

## Scope

This milestone covers the host-facing capability boundary for:

- Codex CLI locatability
- Docker CLI locatability and daemon reachability
- explicit host-context selection for readiness and preflight

It does not cover real Codex execution, G0 execution, or production attempt
creation.

## Normative basis

This milestone is driven by repeated factual blockers observed in runners:

- Codex CLI absent in some contexts
- Docker runtime unavailable in some contexts
- host/session differences that make PATH and token context unreliable as
  implicit authority

The operating contract already treats missing capabilities as boundaries, not
success.

## Invariants

- Capability discovery MUST be explicit and reproducible.
- PATH discovery MUST NOT be authoritative for host selection.
- Host readiness MUST fail closed when a required capability cannot be resolved.
- CLI availability and auth readiness MUST remain separate facts.
- Docker capability and Codex capability MAY differ and MUST be reported
  independently.

## Affected interfaces

- `src/oma7/host_portability.py`
- `src/oma7/codex_runtime.py`
- `src/oma7/docker_lifecycle.py`
- `scripts/oma7-release-candidate-readiness.py`
- `scripts/host-codex-preflight.ps1`

## Acceptance criteria

- The readiness/preflight path can report a supported host context explicitly.
- The same contract distinguishes:
  - CLI absent
  - CLI available but auth not ready
  - Docker unavailable
  - Docker ready
- Tests prove the detector is fail-closed and does not depend on PATH
  accidental discovery.
- The milestone is reflected in roadmap/state docs only after code and tests
  confirm it.

## Architectural limits

- No new execution architecture is introduced.
- No auth or model-call behavior is changed.
- Host portability remains a boundary detector and selector, not an executor.

## Architecture decision

`Host Capability Provisioning` is outside the OMA7 responsibility boundary.
OMA7 may detect, select, and validate whether the current host context is
supported, but it MUST NOT provision Docker Desktop, install Codex, copy
credentials, or otherwise mutate the host into a supported state.

Provisioning is therefore treated as an external operator/host capability
boundary, not a software milestone inside OMA7.

## Next OMA7 block

After host capability portability, the next legitimate OMA7 milestone remains
`Codex sandbox preflight`, which is already represented in the roadmap and can
continue to use the explicit host capability detector as an input.
