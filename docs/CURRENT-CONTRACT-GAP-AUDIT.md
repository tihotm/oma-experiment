# Current Contract Gap Audit

Baseline HEAD: `f1b6391`

Audit scope:

- inspect the current implementation as it exists in this repository
- preserve the historical baseline
- avoid redesign
- avoid promoting test confirmation to execution

Execution status guardrails:

- `REAL CODEX EXEC = 0`
- `REAL CONTAINER G0 = 0`
- `REAL A1 = 0`
- `REAL QUALIFIED PAIRS = 0`

Current test evidence:

- `python -m unittest discover -s tests -v`
- result: `OK`
- this is test confirmation only, not execution of the scientific contract

## Current head summary

The repository currently contains a minimal Python foundation for:

- Git-backed snapshot identity
- frozen snapshot materialization
- evidence applicability checks
- a basic B0 observation normalizer
- a separate qualifier
- a SWE-bench no-patch contract helper
- a small unit-test suite

The implementation is intentionally small and does not yet provide the full
scientific contract requested for OMA7 current-contract convergence.

## Requirement Review

### 1. execution_context_id separated from verification_context_id

Status: `MISSING`

Current code:

- `VerificationContextIdentity` exists in `src/oma7/models.py`
- no separate `ExecutionContextIdentity` exists

Gap:

- execution context and verification context are not modeled as distinct
  identities

### 2. materialization_id separated from subject_id

Status: `MISSING`

Current code:

- `SubjectIdentity` exists in `src/oma7/models.py`
- `SnapshotIdentity` exists in `src/oma7/models.py`
- neither is modeled as a distinct `MaterializationId`

Gap:

- the materialized copy of a submission is not independently identified from
  the subject identity

### 3. scope_policy_id binding

Status: `MISSING`

Current code:

- no scope policy model exists

Gap:

- no explicit binding between scope policy and evidence/verification context

### 4. evidence applicability under all required identities

Status: `PARTIAL`

Current code:

- `EvidenceApplicability` in `src/oma7/models.py` checks subject identity,
  verification context identity, and PASS
- `verify_evidence(...)` in `src/oma7/verifier.py` performs equality checks

Gaps:

- applicability does not include execution context identity
- applicability does not include materialization identity
- applicability does not include scope policy identity
- provenance completeness is not modeled

### 5. executor full process-tree quiescence

Status: `MISSING`

Current code:

- no executor abstraction exists
- no process-tree inspection exists

Gap:

- the repository does not yet model or verify quiescence of an execution tree

### 6. hidden oracle temporal isolation

Status: `MISSING`

Current code:

- no oracle isolation primitive exists
- no temporal fence or time-bounded oracle snapshot exists

Gap:

- hidden oracle contamination is not prevented by a dedicated isolation layer

### 7. fail-closed future-history sanitization/reachability

Status: `MISSING`

Current code:

- no future-history sanitizer exists
- no reachability policy exists for future or historical evidence

Gap:

- the implementation does not yet fail closed on future-history leakage

### 8. atomic evidence publication

Status: `MISSING`

Current code:

- evidence is only represented in memory
- no atomic publish primitive exists

Gap:

- no atomic publication, commit, or CAS-style write path is implemented

### 9. provenance completeness and independent anchor interface

Status: `PARTIAL`

Current code:

- `Evidence` in `src/oma7/models.py` stores a predicate payload
- `protocol/UPSTREAM-PINS-P0.json` captures upstream references

Gaps:

- provenance is not complete as a first-class model
- there is no independent anchor interface
- no subject/materialization/execution provenance chain is modeled end-to-end

### 10. cost-ledger head/event-count binding

Status: `MISSING`

Current code:

- no cost ledger exists

Gap:

- there is no head/event-count binding, no ledger snapshot, and no audit trail

### 11. human-intervention accounting

Status: `MISSING`

Current code:

- no human intervention model exists

Gap:

- no explicit accounting for manual overrides, approvals, or escalations

### 12. scope-control integrity

Status: `PARTIAL`

Current code:

- `AGENTS.md` constrains scope and bans broad classes of systems
- `docs/REUSE-MATRIX.md` records reuse-first decisions

Gaps:

- scope control is documented, but not enforced by a dedicated runtime primitive

### 13. transition/touch history for protected artifacts

Status: `MISSING`

Current code:

- no transition log exists
- no touch history exists for protected artifacts

Gap:

- protected-artifact transitions are not tracked as auditable events

### 14. false-DONE decision boundary

Status: `PARTIAL`

Current code:

- `AGENTS.md` forbids claims without evidence
- tests were executed for the current implementation

Gaps:

- there is no formal decision boundary object
- no machine-enforced false-DONE gate exists

### 15. recovery without carrying stale evidence/oracle/runtime contamination

Status: `MISSING`

Current code:

- `freeze_snapshot(...)` creates a copy of the current workspace
- no recovery protocol exists

Gap:

- recovery semantics and stale contamination cleanup are not modeled

### 16. external-effect idempotency semantics

Status: `MISSING`

Current code:

- no external-effect model exists

Gap:

- idempotency of external side effects is not represented or checked

### 17. concurrent supervision: lease/fencing/CAS semantics

Status: `MISSING`

Current code:

- no lease, fencing token, or CAS primitive exists

Gap:

- concurrent supervision is not modeled

### 18. artifact/reference confusion and materialization binding

Status: `PARTIAL`

Current code:

- Git-backed snapshot identity exists
- frozen snapshot copy exists

Gaps:

- no explicit artifact/reference disambiguation model exists
- no materialization binding object exists

### 19. UNKNOWN/missing-observability fail-closed behavior

Status: `PARTIAL`

Current code:

- `ResultStatus.UNKNOWN` exists in `src/oma7/models.py`
- `_normalize_status(...)` in `src/oma7/swebench_adapter.py` maps unsupported values to `UNKNOWN`

Gap:

- fail-closed behavior is not enforced end-to-end for all observability gaps
- UNKNOWN is represented, but there is no broader missing-observability policy object

### 20. unsupported schema/enum fail-closed behavior

Status: `PARTIAL`

Current code:

- unsupported result values normalize to `UNKNOWN`
- the code does not raise on unsupported enum/schema inputs in all paths

Gap:

- unsupported schema/enum handling is not consistently fail-closed across all
  interfaces

## Current invariant coverage

Current invariant coverage is limited to test-confirmed checks for:

- same subject/context accepts
- mutation of subject/context rejects
- FAIL evidence never authorizes acceptance
- snapshot copy exists and is distinct from the source path
- Git identity changes under content mutation
- SWE-bench no-patch helper ignores `prediction["model_patch"]`

Not yet covered in code:

- execution context identity
- materialization identity
- scope policy binding
- process-tree quiescence
- oracle temporal isolation
- future-history sanitization
- atomic publication
- provenance anchor interface
- cost ledger
- human intervention accounting
- transition history
- concurrency control
- external-effect idempotency

## Evidence model

Current evidence model:

- in-memory `Evidence(subject_identity, verification_context_identity, result, predicate)`
- applicability checks compare subject identity and verification context identity
- acceptance is allowed only when both match and result is PASS

Required evidence model:

- subject identity
- materialization identity
- execution context identity
- verification context identity
- scope policy identity
- provenance anchors
- atomic publication semantics
- fail-closed unsupported-schema handling

Migration required: `YES`

## Status by core axis

SUBJECT_ID_STATUS = `PARTIAL`
MATERIALIZATION_ID_STATUS = `MISSING`
EXECUTION_CONTEXT_STATUS = `MISSING`
VERIFICATION_CONTEXT_STATUS = `PARTIAL`
SCOPE_POLICY_STATUS = `MISSING`
PROVENANCE_STATUS = `PARTIAL`
COST_LEDGER_STATUS = `MISSING`
HUMAN_ACCOUNTING_STATUS = `MISSING`
QUIESCENCE_STATUS = `MISSING`
CONCURRENCY_STATUS = `MISSING`
FAIL_CLOSED_STATUS = `PARTIAL`

## Files inspected

- `src/oma7/models.py`
- `src/oma7/snapshot.py`
- `src/oma7/verifier.py`
- `src/oma7/swebench_adapter.py`
- `tests/test_oma7_core.py`
- `AGENTS.md`
- `docs/REUSE-MATRIX.md`
- `protocol/UPSTREAM-PINS-P0.json`

## Audit conclusion

The current implementation is a valid minimal foundation, but it is not yet the
current scientific contract.

The main gap is structural: the repository models only a subset of the required
identities and does not yet separate execution, materialization, scope policy,
provenance anchors, or concurrency semantics.

The current code should be preserved as baseline evidence, not redesigned away.

## Lot 3 convergence update

Current code and tests now confirm the following requirements in code:

- `SubjectIdentity`
- `MaterializationIdentity`
- `ExecutionContextIdentity`
- `VerificationContextIdentity`
- `ScopePolicyIdentity`
- `ProvenanceAnchorIdentity`
- expanded `Evidence`
- canonical identity hashing
- schema fail-closed parsing

The following remain intentionally out of scope for this lot:

- executor quiescence
- hidden oracle temporal isolation
- atomic publication
- cost ledger
- human intervention accounting
- concurrency lease/fencing/CAS
- recovery engine
- external-effect idempotency

Evidence labels:

- `CODE_CONFIRMED` for the new identity/evidence foundation
- `TEST_CONFIRMED` for the unit tests added in this lot
- `EXECUTED` remains prohibited for the scientific contract

## Lot 4 lifecycle update

This lot adds a supervisor-owned lifecycle model, a single fail-closed
acceptance gate, legitimate no-op decision support, and atomic evidence
publication primitives.

It does not implement runtime quiescence, oracle isolation, recovery
or concurrency supervision.
