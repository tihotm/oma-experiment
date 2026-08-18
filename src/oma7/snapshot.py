from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import shutil
import tempfile

from .git_identity import compute_git_tree_identity
from .models import SnapshotIdentity


def freeze_snapshot(workspace: str | Path) -> tuple[SnapshotIdentity, Path]:
    root = Path(workspace).resolve()
    commit, status_hash, index_hash = compute_git_tree_identity(root)
    snapshot = SnapshotIdentity(root=str(root), git_status=status_hash, git_index=index_hash)
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

