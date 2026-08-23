from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    ROOT / "AGENTS.md",
    ROOT / "docs" / "agent" / "INDEX.md",
    ROOT / "docs" / "agent" / "CURRENT-WORK.md",
    ROOT / "docs" / "CURRENT-STATE.md",
    ROOT / "docs" / "INVARIANTS.md",
    ROOT / "docs" / "SPEC.md",
    ROOT / "docs" / "CLAIM-MAP.md",
    ROOT / "docs" / "LIFECYCLE.md",
    ROOT / "docs" / "ROADMAP.md",
)

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _is_external(link: str) -> bool:
    return link.startswith("http://") or link.startswith("https://") or link.startswith("mailto:")


def _resolve_link(source: Path, link: str) -> Path | None:
    if _is_external(link) or link.startswith("#"):
        return None
    target = link.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None
    return (source.parent / target).resolve()


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED_FILES:
        if not path.exists():
            errors.append(f"missing required file: {path.relative_to(ROOT)}")

    checked = (
        ROOT / "AGENTS.md",
        ROOT / "docs" / "agent" / "INDEX.md",
        ROOT / "docs" / "agent" / "CURRENT-WORK.md",
        ROOT / "docs" / "CURRENT-STATE.md",
        ROOT / "docs" / "INVARIANTS.md",
        ROOT / "docs" / "SPEC.md",
        ROOT / "docs" / "CLAIM-MAP.md",
        ROOT / "docs" / "LIFECYCLE.md",
        ROOT / "docs" / "ROADMAP.md",
    )
    for source in checked:
        if not source.exists():
            continue
        text = source.read_text(encoding="utf-8")
        for link in LINK_RE.findall(text):
            resolved = _resolve_link(source, link)
            if resolved is not None and not resolved.exists():
                errors.append(f"broken link in {source.relative_to(ROOT)} -> {link}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("harness validation ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
