from __future__ import annotations

import hashlib
from dataclasses import asdict
import os
from pathlib import Path
import shutil
import tempfile

from .git_identity import compute_git_tree_identity
from .models import MaterializationIdentity, SubjectIdentity


def _topology_digest(entries: list[str]) -> str:
    payload = "\n".join(sorted(entries))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def freeze_snapshot(workspace: str | Path) -> tuple[MaterializationIdentity, Path]:
    root = Path(workspace).resolve()
    commit, status_hash, index_hash = compute_git_tree_identity(root)
    symlinks: list[str] = []
    hardlinks: list[str] = []
    for current_root, dirs, files in os.walk(root):
        for name in dirs + files:
            candidate = Path(current_root) / name
            try:
                if candidate.is_symlink():
                    symlinks.append(f"{candidate.relative_to(root)}->{os.readlink(candidate)}")
                elif candidate.is_file():
                    stat = candidate.stat()
                    if stat.st_nlink > 1:
                        hardlinks.append(f"{candidate.relative_to(root)}:{stat.st_ino}:{stat.st_nlink}")
            except OSError:
                continue
    subject = SubjectIdentity(git_tree=index_hash, git_commit=commit, path=".")
    snapshot = MaterializationIdentity(
        subject_identity=subject,
        canonical_root_descriptor=f"git:{commit}:{status_hash}:{index_hash}",
        symlink_topology=tuple(sorted(tuple(link.split("->", 1)) for link in symlinks)),
        hardlink_topology=tuple(sorted(tuple(link.split(":", 2)[:2]) for link in hardlinks)),
        worktree_reference_identity=status_hash,
    )
    frozen_dir = Path(tempfile.mkdtemp(prefix="oma7-snapshot-"))
    for item in root.iterdir():
        if item.name == ".git":
            continue
        target = frozen_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    (frozen_dir / ".oma7-snapshot.json").write_text(str(asdict(snapshot)), encoding="utf-8")
    return snapshot, frozen_dir
