"""Enrich ContextBundle metadata for run.json and UI."""

from __future__ import annotations

from typing import Any

from agent_lab.context.bundle import ContextBundle, ContextBundleMeta
from agent_lab.context.limits import agent_context_limits, trim_level


def enrich_bundle_meta(
    meta: ContextBundleMeta,
    bundle: ContextBundle,
    *,
    messages_in_payload: int,
    messages_in_turn: int,
    messages_in_session: int,
) -> None:
    """Mutate meta with budget / trim fields (after layer_chars set)."""
    limits = agent_context_limits()
    total = meta.layer_chars.get("total", len(bundle.render()))
    budget_pct = round(100.0 * total / limits.max_thread_chars, 1) if limits.max_thread_chars > 0 else 0.0
    level = trim_level(
        budget_pct=budget_pct,
        turns_omitted=meta.turns_omitted,
        chars_omitted=meta.chars_omitted,
        limits=limits,
    )
    meta.limits = limits.to_dict()
    meta.budget_pct = budget_pct
    meta.trim_level = level
    meta.messages_in_payload = messages_in_payload
    meta.messages_in_turn = messages_in_turn
    meta.messages_in_session = messages_in_session
    meta.numbered_context = limits.numbered_context


def apply_invoke_follow_to_context_meta(
    context_meta: dict[str, Any],
    combined_follow: str,
) -> None:
    """Add post-render follow blocks (lead/hook/plan clarify) into budget accounting."""
    follow_len = len(combined_follow.strip()) if combined_follow.strip() else 0
    if follow_len <= 0:
        return
    layer = dict(context_meta.get("layer_chars") or {})
    layer["combined_follow"] = follow_len
    layer["total"] = int(layer.get("total", 0)) + follow_len
    context_meta["layer_chars"] = layer
    limits = agent_context_limits()
    total = int(layer["total"])
    budget_pct = round(100.0 * total / limits.max_thread_chars, 1) if limits.max_thread_chars > 0 else 0.0
    context_meta["budget_pct"] = budget_pct
    context_meta["trim_level"] = trim_level(
        budget_pct=budget_pct,
        turns_omitted=int(context_meta.get("turns_omitted") or 0),
        chars_omitted=int(context_meta.get("chars_omitted") or 0),
        limits=limits,
    )


def summarize_turn_context(agents_log: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-agent context meta for run.json last_turn.context."""
    if not agents_log:
        return {}
    totals = [(e.get("layer_chars") or {}).get("total", 0) for e in agents_log]
    levels = [e.get("trim_level", "ok") for e in agents_log]
    worst = "ok"
    if "critical" in levels:
        worst = "critical"
    elif "warn" in levels:
        worst = "warn"
    limits = agent_context_limits()
    return {
        "agent_count": len(agents_log),
        "payload_chars_max": max(totals) if totals else 0,
        "payload_chars_total": sum(totals),
        "trim_level": worst,
        "max_thread_chars": limits.max_thread_chars,
        "any_turns_omitted": any((e.get("turns_omitted") or 0) > 0 for e in agents_log),
        "any_chars_omitted": any((e.get("chars_omitted") or 0) > 0 for e in agents_log),
    }
