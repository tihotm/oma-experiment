# Supervision Contract

Supervision must remain fail-closed and durable.

Canonical sources:

- [src/oma7/control_plane.py](../../src/oma7/control_plane.py)
- [src/oma7/lifecycle.py](../../src/oma7/lifecycle.py)
- [docs/INVARIANTS.md](../INVARIANTS.md)

Rules:

- preserve attempt identity, state, and durability across reload
- do not collapse distinct attempts that share a subject
- do not accept stale evidence after restart
- do not reuse verification unless subject, execution, verification, scope, and provenance bindings still match
- duplicate acceptance is forbidden
- retries are bounded by budget and retry policy

