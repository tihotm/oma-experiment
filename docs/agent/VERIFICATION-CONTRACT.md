# Verification Contract

Verification is binding only when evidence, identities, and scope align.

Canonical sources:

- [src/oma7/lifecycle.py](../../src/oma7/lifecycle.py)
- [src/oma7/models.py](../../src/oma7/models.py)
- [docs/EVIDENCE-MODEL.md](../EVIDENCE-MODEL.md)
- [docs/IDENTITY-MODEL.md](../IDENTITY-MODEL.md)

Rules:

- separate `TEST_CONFIRMED` from `EXECUTED`
- require subject, materialization, execution, verification, scope, and provenance bindings
- reject stale verification after restart or subject change
- preserve no-op and acceptance idempotency semantics

