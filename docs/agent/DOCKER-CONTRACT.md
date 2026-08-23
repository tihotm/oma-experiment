# Docker Contract

Docker support is a production helper plus tests, not a separate implementation.

Canonical sources:

- [src/oma7/docker_lifecycle.py](../../src/oma7/docker_lifecycle.py)
- [tests/test_docker_lifecycle.py](../../tests/test_docker_lifecycle.py)
- [tests/test_supervision_docker.py](../../tests/test_supervision_docker.py)

Rules:

- use argv lists and `subprocess.run`
- do not rely on the old PowerShell wrapper path
- do not modify Docker Desktop ACLs, groups, or daemon exposure
- do not read or copy user credentials
- keep debug output safe and non-secret
- treat sandbox Docker denial as an environment boundary, not a code success

