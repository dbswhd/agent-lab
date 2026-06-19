"""Token/budget visibility helpers for run.json + room context."""

from __future__ import annotations

from typing import Any

from agent_lab.context_limits import agent_context_limits
from agent_lab.context_meta import summarize_turn_context


def _build_entry(
    run_meta: dict[str, Any] | None,
    context_log: list[dict[str, Any]],
    turn_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    limits = agent_context_limits()
    summary = summarize_turn_context(context_log)
    payload_chars_total = int(summary.get("payload_chars_total") or 0)
    payload_chars_max = int(summary.get("payload_chars_max") or 0)

    max_thread_chars = limits.max_thread_chars
    warn_pct = limits.warn_budget_pct
    critical_pct = limits.critical_budget_pct

    payload_budget_pct = round(100.0 * payload_chars_total / max_thread_chars, 1) if max_thread_chars > 0 else 0.0
    warn = payload_budget_pct >= warn_pct
    critical = payload_budget_pct >= critical_pct

    entry: dict[str, Any] = {
        "last_in": payload_chars_max,
        "last_out": payload_chars_total,
        "warn": warn,
        "critical": critical,
        "cumulative_chars": payload_chars_total,
    }
    if turn_meta:
        entry["last_trim_level"] = turn_meta.get("trim_level")
    return entry


def record_run_token_budget(
    run_meta: dict[str, Any] | None,
    context_log: list[dict[str, Any]],
    turn_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if run_meta is None:
        return None
    entry = _build_entry(run_meta, context_log, turn_meta)
    existing = run_meta.get("token_budget")
    if isinstance(existing, dict):
        existing.update(entry)
        return existing
    run_meta["token_budget"] = entry
    return entry
