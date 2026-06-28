"""Edit-time syntax gate (G4) — hard-block merge on changed *.py SyntaxError.

Pure stdlib (ast/py_compile). Default OFF via AGENT_LAB_SYNTAX_GATE: when off, the
``_syntax_gate_check`` is never appended to merge_checks, so the checks list is
byte-identical to today (OFF-parity). Python-only; lint stays non-blocking evidence
elsewhere. Defensive: missing / unreadable / out-of-worktree / non-.py paths are
skipped (treated as not-scanned), never raising.

Scan logic lives in :mod:`syntax_gate_core` (Track 2.0b seam for optional PyO3).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_lab.syntax_gate_core import merge_result_for_syntax_scan, scan_python_syntax

_TRUE = frozenset({"1", "true", "yes", "on"})

_PATH_KEYS = (
    "source_touched_paths",
    "touched_paths",
    "expected_paths",
    "verification_paths",
    "monitored_paths",
)


def syntax_gate_enabled() -> bool:
    """AGENT_LAB_SYNTAX_GATE (default ON): hard-block merge on changed *.py SyntaxError. Opt-out via =0."""
    raw = os.getenv("AGENT_LAB_SYNTAX_GATE")
    if raw is None or raw.strip() == "":
        return True
    return raw.strip().lower() in _TRUE


def _worktree_root(execution: dict[str, Any] | None) -> Path | None:
    if not execution:
        return None
    raw = execution.get("worktree_path") or execution.get("git_root")
    if not raw:
        return None
    try:
        return Path(str(raw)).resolve()
    except (OSError, ValueError):
        return None


def changed_python_files(execution: dict[str, Any] | None) -> list[Path]:
    """Resolve changed *.py files inside the pending execution's worktree."""
    root = _worktree_root(execution)
    if execution is None or root is None:
        return []
    seen: set[Path] = set()
    out: list[Path] = []
    for key in _PATH_KEYS:
        for raw in execution.get(key) or []:
            name = str(raw)
            if not name.endswith(".py"):
                continue
            candidate = Path(name)
            resolved = (candidate if candidate.is_absolute() else (root / candidate)).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            out.append(resolved)
    return sorted(out)


def evaluate_syntax_gate(execution: dict[str, Any] | None) -> dict[str, Any]:
    """Produce the ``{id, ok, detail}`` merge-check result for the syntax gate."""
    if execution is None:
        return {"id": "syntax_gate", "ok": True, "detail": "no pending execution"}
    root = _worktree_root(execution)
    paths = changed_python_files(execution)
    hit = scan_python_syntax(paths, root=root)
    return merge_result_for_syntax_scan(paths, hit)
