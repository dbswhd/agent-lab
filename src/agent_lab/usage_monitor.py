"""Capability-aware usage monitor for the dynamic resilient room.

Honest by construction: proactive preemption is a LOCAL budget/usage-header
heuristic, never a claim of server-side remaining quota. Only usage-exposing
providers (per provider_registry) can be preempted proactively; OAuth/CLI
providers are reactive-only and fail over on confirmed credential errors.
"""

from __future__ import annotations

from typing import Any

from agent_lab import provider_registry
from agent_lab.credential_store import (
    _account_cooled,
    get_provider_accounts,
    is_credential_failure,
    set_provider_accounts,
)

DEFAULT_PREEMPT_THRESHOLD = 0.9
DEFAULT_COOLDOWN_SECONDS = 15 * 60.0


def should_preempt(
    provider: str,
    *,
    spent_usd: float = 0.0,
    budget_usd: float | None = None,
    used_fraction: float | None = None,
    threshold: float = DEFAULT_PREEMPT_THRESHOLD,
) -> bool:
    """LOCAL heuristic: preempt a usage-exposing provider before it likely exhausts.

    - Non usage-exposing providers (OAuth/CLI) are reactive-only -> never preempt.
    - ``used_fraction`` (e.g. from a provider usage header) takes precedence.
    - Else fall back to a local budget cap (spent_usd vs budget_usd).
    - With no signal at all, do not preempt (capability honesty).
    """
    if not provider_registry.is_usage_exposing(provider):
        return False
    if used_fraction is not None:
        return used_fraction >= threshold
    if budget_usd is not None and budget_usd > 0:
        return spent_usd >= budget_usd * threshold
    return False


def provider_spent_usd(run_meta: dict[str, Any] | None, provider: str) -> float:
    """Best-effort local spend for a provider from run_meta['cost_ledger']."""
    if not isinstance(run_meta, dict):
        return 0.0
    ledger = run_meta.get("cost_ledger")
    if not isinstance(ledger, dict):
        return 0.0
    by_agent = ledger.get("by_agent")
    if not isinstance(by_agent, dict):
        return 0.0
    entry = by_agent.get(provider)
    if not isinstance(entry, dict):
        return 0.0
    raw = entry.get("cost_usd")
    return float(raw) if isinstance(raw, (int, float)) else 0.0


def cooldown_active(provider: str, label: str, *, now: float | None = None) -> bool:
    if provider_registry.is_cooldown_exempt(provider):
        return False
    for acct in get_provider_accounts(provider):
        if str(acct.get("label") or "").strip() == label:
            return _account_cooled(acct, now=now)
    return False


def mark_exhausted(
    provider: str,
    label: str,
    *,
    error: object | None = None,
    force: bool = False,
    cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    now: float | None = None,
) -> bool:
    """Set cooldown_until on an account only on a confirmed credential failure.

    Local/cooldown-exempt providers (the offline fallback floor) are never cooled
    so the room always retains >=1 agent. Returns True when a cooldown was applied.
    """
    if provider_registry.is_cooldown_exempt(provider):
        return False
    if not force and not is_credential_failure(error):
        return False
    import time as _time

    base = now if now is not None else _time.time()
    accounts = get_provider_accounts(provider)
    changed = False
    for acct in accounts:
        if str(acct.get("label") or "").strip() == label:
            acct["cooldown_until"] = base + cooldown_seconds
            changed = True
    if changed:
        set_provider_accounts(provider, accounts)
    return changed
