"""Hook · Communicate observability helpers for API and UI."""

from __future__ import annotations

from agent_lab.run.state import RunStateLike
import json
from pathlib import Path
from typing import Any


def trace_tail(folder: Path | None, *, limit: int = 50) -> list[dict[str, Any]]:
    """Last N spans from ``trace.jsonl`` (OTel-lite tracer, G5)."""
    if folder is None:
        return []
    path = folder / "trace.jsonl"
    if not path.is_file():
        return []
    spans: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                spans.append(obj)
    except OSError:
        return []
    return spans[-max(1, limit) :]


def hook_runs_tail(run_meta: RunStateLike | None, *, limit: int = 20) -> list[dict[str, Any]]:
    runs = (run_meta or {}).get("hook_runs") or []
    if not isinstance(runs, list):
        return []
    tail = [r for r in runs if isinstance(r, dict)][-max(1, limit) :]
    return tail


def last_communicate_meta(run_meta: RunStateLike | None) -> dict[str, Any] | None:
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


def dispatch_ledger_tail(run_meta: RunStateLike | None, *, limit: int = 10) -> list[dict[str, Any]]:
    ledger = (run_meta or {}).get("dispatch_ledger") or []
    if not isinstance(ledger, list):
        return []
    return [r for r in ledger if isinstance(r, dict)][-max(1, limit) :]


def observability_snapshot(
    run_meta: RunStateLike | None,
    *,
    folder: Path | None = None,
) -> dict[str, Any]:
    meta = run_meta or {}
    ledger = meta.get("dispatch_ledger") or []
    spans = trace_tail(folder)
    return {
        "hook_runs_tail": hook_runs_tail(meta),
        "hook_run_count": len(meta.get("hook_runs") or []),
        "last_communicate_meta": last_communicate_meta(meta),
        "dispatch_ledger_tail": dispatch_ledger_tail(meta),
        "dispatch_count": len(ledger) if isinstance(ledger, list) else 0,
        "pending_dispatch_intents": len(
            [i for i in (meta.get("dispatch_intents") or []) if isinstance(i, dict) and i.get("status") == "pending"]
        ),
        "trace_tail": spans,
        "trace_span_count": len(spans),
        "token_budget": meta.get("token_budget") if isinstance(meta.get("token_budget"), dict) else None,
        "cost_ledger_cache_hit_rate": (
            float(meta.get("cost_ledger", {}).get("cache_hit_rate") or 0.0)
            if isinstance(meta.get("cost_ledger"), dict)
            else 0.0
        ),
    }
