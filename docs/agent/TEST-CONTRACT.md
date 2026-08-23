# Test Contract

Tests must reflect the real current tree.

Canonical sources:

- [docs/CURRENT-STATE.md](../CURRENT-STATE.md)
- `python -m unittest discover -s tests -v`

Rules:

- keep test names discoverable by `unittest`
- do not preserve stale historical counts as current truth
- distinguish offline, integration, and runtime skips
- a skip in the sandbox must be factual, not hidden as success
- if a behavior is still relevant and missing, add the smallest targeted test

