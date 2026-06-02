#!/usr/bin/env python3
"""CI guard for stale Agent Lab execute worktrees."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from agent_lab.plan_execute_worktree import list_orphan_worktrees  # noqa: E402
from agent_lab.session import SESSIONS_DIR  # noqa: E402

TERMINAL_STATUSES = {"merged", "rejected"}


def _load_run(folder: Path) -> dict[str, Any]:
    path = folder / "run.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _terminal_stale_worktrees(folder: Path, run: dict[str, Any]) -> list[Path]:
    out: list[Path] = []
    for row in run.get("executions") or []:
        if not isinstance(row, dict) or row.get("status") not in TERMINAL_STATUSES:
            continue
        exec_id = str(row.get("id") or "")
        if not exec_id:
            continue
        wt = Path(str(row.get("worktree_path") or folder / "worktrees" / exec_id))
        if not wt.is_absolute():
            wt = folder / wt
        if wt.is_dir():
            out.append(wt)
    return out


def find_stale_worktrees(sessions_dir: Path = SESSIONS_DIR) -> list[str]:
    if not sessions_dir.is_dir():
        return []
    stale: list[str] = []
    for folder in sorted(p for p in sessions_dir.iterdir() if p.is_dir()):
        if folder.name.startswith("."):
            continue
        run = _load_run(folder)
        for path in list_orphan_worktrees(folder, run):
            stale.append(f"{folder.name}: orphan {path}")
        for path in _terminal_stale_worktrees(folder, run):
            stale.append(f"{folder.name}: stale terminal worktree {path}")
    return stale


def main() -> int:
    stale = find_stale_worktrees()
    if not stale:
        print("OK: no stale execute worktrees")
        return 0
    for row in stale:
        print(f"FAIL: {row}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
