from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_git_tree_identity(root: Path) -> tuple[str, str, str]:
    root = root.resolve()
    git_status = _run_git(["status", "--porcelain=v1", "--ignored=matching"], root)
    git_index = _run_git(["ls-files", "-s", "-z"], root)
    git_commit = _run_git(["rev-parse", "HEAD"], root).strip()
    return git_commit, _hash_text(git_status), _hash_text(git_index)


def has_git_repo(path: Path) -> bool:
    if (path / ".git").exists():
        return True
    try:
        return bool(_run_git(["rev-parse", "--git-dir"], path).strip())
    except Exception:
        return False
