#!/usr/bin/env python3
"""One-shot: move mission_*.py → mission/ and rewrite agent_lab.mission_* imports."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_lab"
MISSION_DIR = SRC / "mission"

IMPORT_REWRITES = ((re.compile(r"\bagent_lab\.mission_(\w+)"), r"agent_lab.mission.\1"),)

SCAN_ROOTS = (SRC, ROOT / "app", ROOT / "tests", ROOT / "scripts")


def _rewrite_imports(text: str) -> str:
    for pattern, repl in IMPORT_REWRITES:
        text = pattern.sub(repl, text)
    return text


def move_modules() -> list[tuple[str, str]]:
    MISSION_DIR.mkdir(exist_ok=True)
    moved: list[tuple[str, str]] = []
    for path in sorted(SRC.glob("mission_*.py")):
        target_stem = path.stem[len("mission_") :]
        target = MISSION_DIR / f"{target_stem}.py"
        content = _rewrite_imports(path.read_text(encoding="utf-8"))
        target.write_text(content, encoding="utf-8")
        path.unlink()
        moved.append((path.name, target.name))
    init = MISSION_DIR / "__init__.py"
    if not init.is_file():
        init.write_text(
            '"""Mission loop, board, scheduler, and templates."""\n\nfrom __future__ import annotations\n',
            encoding="utf-8",
        )
    return moved


def rewrite_repo_imports() -> int:
    changed = 0
    for base in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if path.is_relative_to(MISSION_DIR):
                continue
            if path.name.startswith("migrate_") and "package" in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            new_text = _rewrite_imports(text)
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
                changed += 1
    return changed


def main() -> None:
    moved = move_modules()
    print(f"Moved {len(moved)} modules into src/agent_lab/mission/")
    for old, new in moved:
        print(f"  {old} -> mission/{new}")
    n = rewrite_repo_imports()
    print(f"Rewrote imports in {n} files")


if __name__ == "__main__":
    main()
