#!/usr/bin/env python3
"""One-shot: move kimi_*.py → kimi/ and rewrite agent_lab.kimi_* imports."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_lab"
KIMI_DIR = SRC / "kimi"

IMPORT_REWRITES = (
    (re.compile(r"\bagent_lab\.kimi_work_(\w+)"), r"agent_lab.kimi.work_\1"),
    (re.compile(r"\bagent_lab\.kimi_(\w+)"), r"agent_lab.kimi.\1"),
)

SCAN_ROOTS = (
    SRC,
    ROOT / "app",
    ROOT / "tests",
    ROOT / "scripts",
)


def _target_name(stem: str) -> str:
    if stem.startswith("kimi_work_"):
        return "work_" + stem[len("kimi_work_") :]
    if stem.startswith("kimi_"):
        return stem[len("kimi_") :]
    raise ValueError(stem)


def _rewrite_imports(text: str) -> str:
    for pattern, repl in IMPORT_REWRITES:
        text = pattern.sub(repl, text)
    return text


def move_modules() -> list[tuple[str, str]]:
    KIMI_DIR.mkdir(exist_ok=True)
    moved: list[tuple[str, str]] = []
    for path in sorted(SRC.glob("kimi_*.py")):
        target_stem = _target_name(path.stem)
        target = KIMI_DIR / f"{target_stem}.py"
        content = _rewrite_imports(path.read_text(encoding="utf-8"))
        target.write_text(content, encoding="utf-8")
        path.unlink()
        moved.append((path.name, target.name))
    init = KIMI_DIR / "__init__.py"
    if not init.is_file():
        init.write_text(
            '"""Kimi / Kimi Work provider adapters and loop integration."""\n\nfrom __future__ import annotations\n',
            encoding="utf-8",
        )
    return moved


def rewrite_repo_imports() -> int:
    changed = 0
    for base in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if path.is_relative_to(KIMI_DIR):
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
    print(f"Moved {len(moved)} modules into src/agent_lab/kimi/")
    for old, new in moved:
        print(f"  {old} -> kimi/{new}")
    n = rewrite_repo_imports()
    print(f"Rewrote imports in {n} files")


if __name__ == "__main__":
    main()
