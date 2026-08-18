# Identity Model

OMA7 now models the following identities as separate first-class concepts:

- `SubjectIdentity`
- `MaterializationIdentity`
- `ExecutionContextIdentity`
- `VerificationContextIdentity`
- `ScopePolicyIdentity`
- `ProvenanceAnchorIdentity`

## Subject identity

`SubjectIdentity` remains Git-backed and describes the logical frozen subject.
It is not sufficient to represent the full materialization/runtime topology.

## Materialization identity

`MaterializationIdentity` binds the logical subject to observable materialization
features such as:

- canonical root descriptor
- symlink topology
- hardlink topology
- worktree/reference identity
- mounted reference artifact identities
- cache manifest digest

## Execution context identity

`ExecutionContextIdentity` captures immutable execution-time inputs such as:

- environment/container image digest
- Codex binary digest
- Codex version
- model
- reasoning level
- harness identity
- dependency lock digest
- dataset revision
- toolchain identity

Missing mandatory digest-like values fail closed.

## Verification context identity

`VerificationContextIdentity` captures verification-time inputs such as:

- dataset revision
- oracle/test_patch identity
- `FAIL_TO_PASS`
- `PASS_TO_PASS`
- harness identity
- verification configuration digest
- verifier/environment image digest
- verifier identity

## Scope policy identity

`ScopePolicyIdentity` captures scope/budget/exception policy and is hashed
canonically so semantically equivalent inputs converge to the same identity.

## Provenance anchor identity

`ProvenanceAnchorIdentity` is a binding abstraction for future composition with
in-toto or Witness. It does not implement a custom attestation system.

