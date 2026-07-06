"""Real token/USD accounting for room missions (G1 economics layer).

Distinct from ``token_budget.py`` (which tracks *payload character* budget for
context trimming). This module records *authoritative* token + cost numbers
extracted from each agent bridge response and accumulates them into
``run.json.cost_ledger``.

Mirrors the ``token_budget.record_run_token_budget`` pattern: it mutates the
in-memory ``run_meta`` dict in place and lets the normal turn-boundary persist
flow write it to disk (writing mid-turn via ``patch_run_meta`` would race with
the turn-end ``_write_session_files`` rebuild and be clobbered).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_lab.agent.models import estimate_cost_usd
from agent_lab.run.state import RunState, RunStateLike


@dataclass
class AgentUsage:
    """One agent invocation's authoritative usage, normalized across bridges."""

    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cache_creation: int = 0
    usd: float | None = None  # provider-reported cost; None → estimate via pricing
    model: str | None = None
    source: str = "provider"  # provider | estimated

    def resolved_usd(self) -> float:
        if self.usd is not None:
            return float(self.usd)
        return estimate_cost_usd(
            self.model,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            cache_read=self.cache_read,
        )


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def usage_from_bridge(data: dict[str, Any] | None) -> AgentUsage | None:
    """Normalize a bridge ``usage`` event payload into ``AgentUsage``.

    Accepts both the Anthropic ``usage`` shape (``input_tokens`` /
    ``output_tokens`` / ``cache_read_input_tokens`` /
    ``cache_creation_input_tokens``) and a pre-flattened shape. Returns ``None``
    when no token/cost signal is present.
    """
    if not isinstance(data, dict):
        return None
    usd_raw = data.get("usd")
    if usd_raw is None:
        usd_raw = data.get("total_cost_usd")
    usage = AgentUsage(
        tokens_in=_as_int(data.get("tokens_in") or data.get("input_tokens")),
        tokens_out=_as_int(data.get("tokens_out") or data.get("output_tokens")),
        cache_read=_as_int(data.get("cache_read") or data.get("cache_read_input_tokens")),
        cache_creation=_as_int(data.get("cache_creation") or data.get("cache_creation_input_tokens")),
        usd=float(usd_raw) if usd_raw is not None else None,
        model=(str(data["model"]) if data.get("model") else None),
        source=str(data.get("usage_source") or data.get("source") or "provider"),
    )
    if not any(
        (
            usage.tokens_in,
            usage.tokens_out,
            usage.cache_read,
            usage.cache_creation,
            usage.usd,
        )
    ):
        return None
    return usage


_DEFAULT_CHARS_PER_TOKEN = 2.0


def _chars_per_token() -> float:
    raw = os.getenv("AGENT_LAB_CHARS_PER_TOKEN")
    if raw is None:
        return _DEFAULT_CHARS_PER_TOKEN
    try:
        val = float(raw.strip())
    except (TypeError, ValueError):
        return _DEFAULT_CHARS_PER_TOKEN
    return val if val > 0 else _DEFAULT_CHARS_PER_TOKEN


def chars_to_tokens(chars: int) -> int:
    """Heuristic for KR/EN mixed agent payloads when provider usage is absent."""
    return max(0, int(float(chars) / _chars_per_token()))


def estimate_usage_from_text(
    *,
    input_chars: int = 0,
    output_chars: int = 0,
    model: str | None = None,
) -> AgentUsage:
    """Fallback usage from rendered context + reply body (OAuth / opaque bridges)."""
    tokens_in = chars_to_tokens(input_chars)
    tokens_out = chars_to_tokens(output_chars)
    if not tokens_in and not tokens_out:
        return AgentUsage(model=model, source="estimated")
    return AgentUsage(
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model=model,
        source="estimated",
    )


def persist_cost_ledger(folder: Path | None, run_meta: RunStateLike | None) -> None:
    """Write in-memory ``cost_ledger`` to run.json without clobbering other fields."""
    if folder is None or not isinstance(run_meta, dict):
        return
    ledger = run_meta.get("cost_ledger")
    if not isinstance(ledger, dict):
        return
    from agent_lab.run.meta import patch_run_meta

    def _patch(run: RunState) -> RunState:
        run["cost_ledger"] = ledger
        return run

    patch_run_meta(folder, _patch)
    # F8: roll session spend into quarterly ledger (and optional autonomy demotion).
    try:
        from agent_lab.cost_ledger_quarter import sync_session_to_quarter

        sync_session_to_quarter(folder, run_meta)
    except Exception:
        pass


def _empty_agent_entry() -> dict[str, Any]:
    return {
        "calls": 0,
        "provider_calls": 0,
        "estimated_calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cache_read": 0,
        "cache_creation": 0,
        "usd": 0.0,
    }


def _recompute_cumulative(ledger: dict[str, Any]) -> None:
    by_agent = ledger.get("by_agent")
    if not isinstance(by_agent, dict):
        by_agent = {}
    cumulative = _empty_agent_entry()
    for entry in by_agent.values():
        if not isinstance(entry, dict):
            continue
        for key in cumulative:
            cumulative[key] += entry.get(key, 0) or 0
    cumulative["usd"] = round(cumulative["usd"], 6)
    ledger["cumulative"] = cumulative
    total_in = cumulative["tokens_in"]
    ledger["cache_hit_rate"] = round(cumulative["cache_read"] / total_in, 4) if total_in > 0 else 0.0


def record_agent_usage(
    run_meta: RunStateLike | None,
    agent_id: str,
    usage: AgentUsage | None,
    *,
    turn: int | None = None,
    source: str | None = None,
) -> dict[str, Any] | None:
    """Accumulate one agent call's usage into run_meta cost_ledger.

    Mutates ``run_meta`` in place (see module docstring) and returns the ledger.
    No-op when ``run_meta`` or ``usage`` is missing.
    """
    if run_meta is None or usage is None:
        return None
    ledger = run_meta.get("cost_ledger")
    if not isinstance(ledger, dict):
        ledger = {"by_agent": {}, "cumulative": _empty_agent_entry(), "cache_hit_rate": 0.0}
    by_agent = ledger.setdefault("by_agent", {})
    entry = by_agent.get(agent_id)
    if not isinstance(entry, dict):
        entry = _empty_agent_entry()
    entry["calls"] = entry.get("calls", 0) + 1
    usage_source = source or usage.source or "provider"
    if usage_source == "estimated":
        entry["estimated_calls"] = int(entry.get("estimated_calls") or 0) + 1
    else:
        entry["provider_calls"] = int(entry.get("provider_calls") or 0) + 1
    entry["tokens_in"] = entry.get("tokens_in", 0) + usage.tokens_in
    entry["tokens_out"] = entry.get("tokens_out", 0) + usage.tokens_out
    entry["cache_read"] = entry.get("cache_read", 0) + usage.cache_read
    entry["cache_creation"] = entry.get("cache_creation", 0) + usage.cache_creation
    entry["usd"] = round(entry.get("usd", 0.0) + usage.resolved_usd(), 6)
    by_agent[agent_id] = entry
    _recompute_cumulative(ledger)
    if turn is not None:
        ledger["updated_at_turn"] = int(turn)
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, cost_ledger=ledger)
    return ledger


def _budget_limit_usd() -> float | None:
    raw = (os.getenv("AGENT_LAB_MISSION_BUDGET_USD") or "").strip()
    if not raw:
        return None
    try:
        limit = float(raw)
    except ValueError:
        return None
    return limit if limit > 0 else None


def _warn_pct() -> float:
    raw = (os.getenv("AGENT_LAB_BUDGET_WARN_PCT") or "").strip()
    try:
        pct = float(raw)
    except ValueError:
        pct = 80.0
    return pct if 0 < pct <= 100 else 80.0


def budget_status(run_meta: RunStateLike | None) -> dict[str, Any]:
    """Return mission budget status for the current cost_ledger.

    ``limit_usd`` is None when ``AGENT_LAB_MISSION_BUDGET_USD`` is unset (no cap).
    """
    spent = 0.0
    if isinstance(run_meta, dict):
        ledger = run_meta.get("cost_ledger")
        if isinstance(ledger, dict):
            cumulative = ledger.get("cumulative")
            if isinstance(cumulative, dict):
                spent = float(cumulative.get("usd", 0.0) or 0.0)
    limit = _budget_limit_usd()
    warn_pct = _warn_pct()
    over = limit is not None and spent >= limit
    warn = limit is not None and spent >= limit * (warn_pct / 100.0)
    return {
        "limit_usd": limit,
        "spent_usd": round(spent, 6),
        "warn_pct": warn_pct,
        "over": over,
        "warn": warn,
    }


def _session_token_budget() -> int | None:
    """Session cumulative-token cap from ``AGENT_LAB_SESSION_TOKEN_BUDGET`` (unset → no cap)."""
    raw = (os.getenv("AGENT_LAB_SESSION_TOKEN_BUDGET") or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _cumulative_tokens(run_meta: RunStateLike | None) -> tuple[int, int]:
    if isinstance(run_meta, dict):
        ledger = run_meta.get("cost_ledger")
        if isinstance(ledger, dict):
            cumulative = ledger.get("cumulative")
            if isinstance(cumulative, dict):
                return (
                    int(cumulative.get("tokens_in", 0) or 0),
                    int(cumulative.get("tokens_out", 0) or 0),
                )
    return 0, 0


def session_budget_action(run_meta: RunStateLike | None) -> dict[str, Any]:
    """Surface cumulative session cost and decide adaptive-efficiency action.

    Combines the existing USD ``budget_status`` with an optional cumulative-token
    cap. ``surface`` is always True so callers can show live cost even with no
    budget set; ``warn``/``over`` are True only when a budget (USD or token) is
    configured and crossed. ``over`` is the OR of the USD and token caps.
    """
    usd = budget_status(run_meta)
    tokens_in, tokens_out = _cumulative_tokens(run_meta)
    tokens_total = tokens_in + tokens_out
    usd_limit = usd.get("limit_usd")
    token_limit = _session_token_budget()
    warn_pct = float(usd.get("warn_pct", 80.0) or 80.0)
    token_over = token_limit is not None and tokens_total >= token_limit
    token_warn = token_limit is not None and tokens_total >= token_limit * (warn_pct / 100.0)
    over = bool(usd.get("over")) or token_over
    warn = bool(usd.get("warn")) or token_warn
    return {
        "cumulative": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "tokens_total": tokens_total,
            "usd": float(usd.get("spent_usd", 0.0) or 0.0),
        },
        "surface": True,
        "budget_set": usd_limit is not None or token_limit is not None,
        "usd_limit": usd_limit,
        "token_limit": token_limit,
        "warn": warn,
        "over": over,
        "suggest_efficiency": over,
    }
