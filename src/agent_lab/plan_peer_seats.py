"""Plan workflow peer-review seats — scribe, architect/critic mapping, cold critic policy."""

from __future__ import annotations

import os
from typing import Any

from agent_lab.agents.registry import AGENT_IDS
from agent_lab import provider_registry

_FALSE = frozenset({"0", "false", "no", "off"})
_TRUE = frozenset({"1", "true", "yes", "on"})

# Preference order when no ROOM_SCRIBE_AGENT env is set and multiple agents are available.
# New agents not listed here fall through to first-in-active order.
_SCRIBE_PREFERENCE: tuple[str, ...] = ("claude", "codex", "cursor")


def _valid_agent_ids() -> frozenset[str]:
    """All registered provider IDs — superset of AGENT_IDS, includes kimi/kimi_work/local."""
    return frozenset(provider_registry.provider_ids()) | frozenset(AGENT_IDS)


def _env_true(key: str) -> bool:
    return os.getenv(key, "").strip().lower() in _TRUE


def session_room_preset(run_meta: dict[str, Any] | None) -> str:
    return str((run_meta or {}).get("room_preset") or "").strip().lower()


def plan_scribe_agent(
    *,
    run_meta: dict[str, Any] | None = None,
    active: list[str] | None = None,
) -> str:
    """Scribe seat for plan.md, resolved from the active roster.

    Resolution order:
    1. ROOM_SCRIBE_AGENT env — honoured when the value is a registered agent and
       present in *active* (or when *active* is not provided).
    2. First agent in *active* that matches _SCRIBE_PREFERENCE.
    3. First agent in *active* (any registered id).
    4. "claude" — last-resort when no active roster is supplied.
    """
    _ = run_meta
    valid = _valid_agent_ids()
    raw = os.getenv("ROOM_SCRIBE_AGENT", "").strip().lower()
    if raw and raw in valid:
        if active is None:
            return raw
        pool = [str(a).strip().lower() for a in active]
        if raw in pool:
            return raw
    if active:
        pool = [str(a).strip().lower() for a in active if str(a).strip().lower() in valid]
        for candidate in _SCRIBE_PREFERENCE:
            if candidate in pool:
                return candidate
        if pool:
            return pool[0]
    return "claude"


def plan_peer_review_seats(
    active: list[str],
    *,
    run_meta: dict[str, Any] | None = None,
) -> list[str]:
    """Ordered peer reviewer ids — non-scribe agents from the active roster, up to 2.

    Role-lane ordering (architect first, critic second) is preserved: whoever
    appears first in *active* after the scribe is removed becomes the architect,
    the next becomes the critic.  No agent name is hardcoded — kimi_work, cursor,
    or any future provider participates as long as it is in the active roster.
    """
    scribe = plan_scribe_agent(run_meta=run_meta, active=active)
    valid = _valid_agent_ids()
    pool = [str(a).strip().lower() for a in active if str(a).strip().lower() in valid]
    reviewers = [a for a in pool if a != scribe][:2]
    return reviewers if reviewers else pool[:2]


def plan_cold_critic_enabled(*, run_meta: dict[str, Any] | None = None) -> bool:
    """Fresh-eyes cold critic for PEER_REVIEW (supervisor preset default-on)."""
    if _env_true("AGENT_LAB_PLAN_COLD_CRITIC"):
        return True
    if session_room_preset(run_meta) == "supervisor":
        return True
    from agent_lab.turn_modes import antidrift_enabled

    return antidrift_enabled()


def plan_peer_review_uses_role_lanes(*, run_meta: dict[str, Any] | None = None) -> bool:
    """Supervisor preset runs architect then critic as separate rounds."""
    return session_room_preset(run_meta) == "supervisor"
