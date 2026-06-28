#!/usr/bin/env python3
"""One-shot: move session.py + session_*.py → session/ and rewrite imports."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_lab"
SESSION_DIR = SRC / "session"

IMPORT_REWRITES = (
    (re.compile(r"\bagent_lab\.session_paths\b"), r"agent_lab.session.paths"),
    (re.compile(r"\bagent_lab\.session_(\w+)"), r"agent_lab.session.\1"),
)

SCAN_ROOTS = (
    SRC,
    ROOT / "app",
    ROOT / "tests",
    ROOT / "scripts",
)


def _rewrite_imports(text: str) -> str:
    for pattern, repl in IMPORT_REWRITES:
        text = pattern.sub(repl, text)
    return text


def move_modules() -> list[tuple[str, str]]:
    SESSION_DIR.mkdir(exist_ok=True)
    moved: list[tuple[str, str]] = []

    for path in sorted(SRC.glob("session_*.py")):
        target_stem = path.stem[len("session_") :]
        target = SESSION_DIR / f"{target_stem}.py"
        content = _rewrite_imports(path.read_text(encoding="utf-8"))
        target.write_text(content, encoding="utf-8")
        path.unlink()
        moved.append((path.name, target.name))

    legacy = SRC / "session.py"
    if legacy.is_file():
        init_content = _rewrite_imports(legacy.read_text(encoding="utf-8"))
        init_path = SESSION_DIR / "__init__.py"
        if not init_path.is_file():
            init_path.write_text(init_content, encoding="utf-8")
        legacy.unlink()
        moved.append(("session.py", "__init__.py"))

    return moved


def rewrite_repo_imports() -> int:
    changed = 0
    for base in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if path.is_relative_to(SESSION_DIR):
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
    print(f"Moved {len(moved)} modules into src/agent_lab/session/")
    for old, new in moved:
        print(f"  {old} -> session/{new}")
    n = rewrite_repo_imports()
    print(f"Rewrote imports in {n} files")


if __name__ == "__main__":
    main()
