# Claim Map

- `same(subject identity)` AND `same(verification context identity)` AND `PASS`
  authorizes acceptance.
- `FAIL` never authorizes acceptance.
- `UNKNOWN` never upgrades to `PASS`.
- Snapshot identity is derived from Git tree/index/status semantics.
- B0 adapter extracts facts only; qualification is separate.

