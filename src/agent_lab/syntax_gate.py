"""Edit-time syntax gate (G4) — hard-block merge on changed *.py SyntaxError.

Pure stdlib (ast/py_compile). Default OFF via AGENT_LAB_SYNTAX_GATE: when off, the
``_syntax_gate_check`` is never appended to merge_checks, so the checks list is
byte-identical to today (OFF-parity). Python-only; lint stays non-blocking evidence
elsewhere. Defensive: missing / unreadable / out-of-worktree / non-.py paths are
skipped (treated as not-scanned), never raising.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_TRUE = frozenset({"1", "true", "yes", "on"})

# Pending-execution path fields that may name changed files (mirrors
# plan_execute_verify._merged_verify_paths key order for determinism).
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
    """Resolve changed *.py files inside the pending execution's worktree.

    Deterministic, deduplicated, sorted. Skips non-.py names and any path that
    resolves outside the worktree root. Existence/readability is checked at scan
    time, not here.
    """
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
            # Stay inside the worktree.
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            out.append(resolved)
    return sorted(out)


def _scan_syntax(paths: list[Path], root: Path | None = None) -> tuple[str, int] | None:
    """Return the first ``(display_path, lineno)`` whose source fails to compile.

    Files are scanned in the given order (changed_python_files already sorts), so
    the first error is deterministic. Missing or unreadable files are skipped.
    Returns None when every readable file parses.
    """
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            compile(source, str(path), "exec")
        except SyntaxError as exc:
            display = path
            if root is not None:
                try:
                    display = path.relative_to(root)
                except ValueError:
                    display = path
            return (str(display), exc.lineno or 0)
        except ValueError:
            # e.g. source contains null bytes — not a SyntaxError; skip defensively.
            continue
    return None


def evaluate_syntax_gate(execution: dict[str, Any] | None) -> dict[str, Any]:
    """Produce the ``{id, ok, detail}`` merge-check result for the syntax gate.

    Always returns ok:True when there is no pending execution, no changed *.py,
    or all changed *.py parse. Returns ok:False with ``detail="file:line"`` on the
    first SyntaxError.
    """
    if execution is None:
        return {"id": "syntax_gate", "ok": True, "detail": "no pending execution"}
    root = _worktree_root(execution)
    paths = changed_python_files(execution)
    if not paths:
        return {"id": "syntax_gate", "ok": True, "detail": "no changed .py"}
    hit = _scan_syntax(paths, root=root)
    if hit is None:
        return {"id": "syntax_gate", "ok": True, "detail": f"{len(paths)} .py ok"}
    file, line = hit
    return {"id": "syntax_gate", "ok": False, "detail": f"{file}:{line}"}
