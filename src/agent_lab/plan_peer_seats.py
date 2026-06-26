"""Plan workflow peer-review seats — scribe, architect/critic mapping, cold critic policy."""

from __future__ import annotations

import os
from typing import Any

from agent_lab.agents.registry import AGENT_IDS

_FALSE = frozenset({"0", "false", "no", "off"})
_TRUE = frozenset({"1", "true", "yes", "on"})


def _env_true(key: str) -> bool:
    return os.getenv(key, "").strip().lower() in _TRUE


def session_room_preset(run_meta: dict[str, Any] | None) -> str:
    return str((run_meta or {}).get("room_preset") or "").strip().lower()


def plan_scribe_agent(*, run_meta: dict[str, Any] | None = None) -> str:
    """Scribe seat for plan.md (``ROOM_SCRIBE_AGENT``, default claude)."""
    _ = run_meta
    raw = (os.getenv("ROOM_SCRIBE_AGENT") or "claude").strip().lower()
    return raw if raw in AGENT_IDS else "claude"


def plan_peer_review_seats(
    active: list[str],
    *,
    run_meta: dict[str, Any] | None = None,
) -> list[str]:
    """Ordered peer reviewer ids (exclude scribe). Supervisor → codex architect, claude critic."""
    scribe = plan_scribe_agent(run_meta=run_meta)
    pool = [str(a).strip().lower() for a in active if str(a).strip().lower() in AGENT_IDS]
    if session_room_preset(run_meta) == "supervisor":
        seats: list[str] = []
        for agent_id in ("codex", "claude"):
            if agent_id in pool and agent_id != scribe and agent_id not in seats:
                seats.append(agent_id)
        if seats:
            return seats[:2]
    reviewers = [a for a in pool if a != scribe][:2]
    if reviewers:
        return reviewers
    return pool[:2]


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
