# Documentation Consistency Audit

FILES_CHECKED

- `docs/CURRENT-STATE.md`
- `docs/INVARIANTS.md`
- `docs/CANONICAL-INVARIANT-REGISTRY.md`
- `PRE-G0-INVARIANT-PRIORITY.md`

CONFLICTS_FOUND

- `docs/CURRENT-STATE.md` uses aggregate implementation buckets that are not 1:1 with the canonical invariant registry.
- `docs/INVARIANTS.md` retains implementation/runtime labels that are distinct from contract-gap taxonomy.

CORRECTIONS_APPLIED

- added canonical registry pointers to `docs/CURRENT-STATE.md` and `docs/INVARIANTS.md`
- clarified that `docs/CANONICAL-INVARIANT-REGISTRY.md` is the 1:1 source for I1-I44

OVERCLAIMS_REMOVED

- none

STALE_COUNTS_UPDATED

- none

UNRESOLVED_AMBIGUITIES

- contract-gap taxonomy remains distinct from invariant registry taxonomy by design

