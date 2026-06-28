#!/usr/bin/env python3
"""One-shot: move agent_*.py → agent/ and rewrite agent_lab.agent_* imports."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_lab"
AGENT_DIR = SRC / "agent"

IMPORT_REWRITES = ((re.compile(r"\bagent_lab\.agent_(\w+)"), r"agent_lab.agent.\1"),)

SCAN_ROOTS = (SRC, ROOT / "app", ROOT / "tests", ROOT / "scripts")

LEGACY_IMPORT_RE = re.compile(
    r"from agent_lab import (agent_[a-z_]+(?:,\s*agent_[a-z_]+)*)"
)


def _rewrite_imports(text: str) -> str:
    for pattern, repl in IMPORT_REWRITES:
        text = pattern.sub(repl, text)
    return text


def _rewrite_legacy_imports(text: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        names = [part.strip() for part in match.group(1).split(",")]
        lines = []
        for name in names:
            if not name.startswith("agent_"):
                lines.append(name)
                continue
            mod = name[len("agent_") :]
            lines.append(f"from agent_lab.agent.{mod} import {name.split(' as ')[0]}")
        return "\n".join(lines) if len(lines) > 1 else lines[0]

    return LEGACY_IMPORT_RE.sub(_repl, text)


def move_modules() -> list[tuple[str, str]]:
    AGENT_DIR.mkdir(exist_ok=True)
    moved: list[tuple[str, str]] = []
    for path in sorted(SRC.glob("agent_*.py")):
        target_stem = path.stem[len("agent_") :]
        target = AGENT_DIR / f"{target_stem}.py"
        content = _rewrite_imports(path.read_text(encoding="utf-8"))
        target.write_text(content, encoding="utf-8")
        path.unlink()
        moved.append((path.name, target.name))
    init = AGENT_DIR / "__init__.py"
    if not init.is_file():
        init.write_text(
            '"""Agent infrastructure: roster, health, permissions, envelopes."""\n\nfrom __future__ import annotations\n',
            encoding="utf-8",
        )
    return moved


def rewrite_repo_imports() -> int:
    changed = 0
    for base in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if path.is_relative_to(AGENT_DIR):
                continue
            if path.name.startswith("migrate_") and "package" in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            new_text = _rewrite_legacy_imports(_rewrite_imports(text))
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
                changed += 1
    return changed


def main() -> None:
    moved = move_modules()
    print(f"Moved {len(moved)} modules into src/agent_lab/agent/")
    for old, new in moved:
        print(f"  {old} -> agent/{new}")
    n = rewrite_repo_imports()
    print(f"Rewrote imports in {n} files")


if __name__ == "__main__":
    main()
