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


def dispatch_ledger_tail(run_meta: dict[str, Any] | None, *, limit: int = 10) -> list[dict[str, Any]]:
    ledger = (run_meta or {}).get("dispatch_ledger") or []
    if not isinstance(ledger, list):
        return []
    return [r for r in ledger if isinstance(r, dict)][-max(1, limit) :]


def observability_snapshot(run_meta: dict[str, Any] | None) -> dict[str, Any]:
    meta = run_meta or {}
    ledger = meta.get("dispatch_ledger") or []
    return {
        "hook_runs_tail": hook_runs_tail(meta),
        "hook_run_count": len(meta.get("hook_runs") or []),
        "last_communicate_meta": last_communicate_meta(meta),
        "dispatch_ledger_tail": dispatch_ledger_tail(meta),
        "dispatch_count": len(ledger) if isinstance(ledger, list) else 0,
        "pending_dispatch_intents": len(
            [i for i in (meta.get("dispatch_intents") or []) if isinstance(i, dict) and i.get("status") == "pending"]
        ),
    }
