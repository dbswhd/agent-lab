"""Hook · Communicate observability helpers for API and UI."""

from __future__ import annotations

from typing import Any


def hook_runs_tail(run_meta: dict[str, Any] | None, *, limit: int = 20) -> list[dict[str, Any]]:
    runs = (run_meta or {}).get("hook_runs") or []
    if not isinstance(runs, list):
        return []
    tail = [r for r in runs if isinstance(r, dict)][-max(1, limit) :]
    return tail


def last_communicate_meta(run_meta: dict[str, Any] | None) -> dict[str, Any] | None:
    turns = (run_meta or {}).get("turns") or []
    if not isinstance(turns, list):
        return None
    for turn in reversed(turns):
        if not isinstance(turn, dict):
            continue
        meta = turn.get("communicate_meta")
        if isinstance(meta, dict):
            return meta
    return None


def observability_snapshot(run_meta: dict[str, Any] | None) -> dict[str, Any]:
    meta = run_meta or {}
    return {
        "hook_runs_tail": hook_runs_tail(meta),
        "hook_run_count": len(meta.get("hook_runs") or []),
        "last_communicate_meta": last_communicate_meta(meta),
    }
