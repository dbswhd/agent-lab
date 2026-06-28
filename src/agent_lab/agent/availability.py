"""Per-turn agent availability — usage-limit pauses without changing user model sets."""

from __future__ import annotations

import re
import time
from typing import Any, Callable

from agent_lab.agents.registry import AgentId, label

_USAGE_LIMIT_PATTERNS = (
    r"usage limit",
    r"rate limit",
    r"\b429\b",
    r"\bquota\b",
    r"credit balance",
    r"insufficient_quota",
    r"overloaded",
)

_AGENT_PROVIDER: dict[str, str] = {
    "cursor": "cursor",
    "codex": "codex",
    "claude": "claude",
    "kimi": "kimi",
    "kimi_work": "kimi_work",
    "local": "local",
}

DEFAULT_USAGE_PAUSE_SEC = 15 * 60.0


def is_usage_limit_error(exc_or_text: object) -> bool:
    text = str(exc_or_text or "").strip().lower()
    if not text:
        return False
    return any(re.search(pat, text) for pat in _USAGE_LIMIT_PATTERNS)


def agent_provider_id(agent_id: str) -> str:
    return _AGENT_PROVIDER.get(str(agent_id).strip().lower(), str(agent_id).strip().lower())


def _pause_map(run_meta: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(run_meta, dict):
        return {}
    raw = run_meta.get("_agent_pauses")
    return raw if isinstance(raw, dict) else {}


def _prune_expired_pauses(run_meta: dict[str, Any] | None, *, now: float | None = None) -> None:
    if not isinstance(run_meta, dict):
        return
    base = now if now is not None else time.time()
    pauses = _pause_map(run_meta)
    if not pauses:
        return
    kept = {
        aid: row
        for aid, row in pauses.items()
        if isinstance(row, dict) and float(row.get("until") or 0) > base
    }
    if kept:
        run_meta["_agent_pauses"] = kept
    else:
        run_meta.pop("_agent_pauses", None)


def agent_pause_until(run_meta: dict[str, Any] | None, agent_id: str, *, now: float | None = None) -> float | None:
    """Return monotonic-unix pause expiry for an agent, or None when active."""
    if not isinstance(run_meta, dict):
        return None
    _prune_expired_pauses(run_meta, now=now)
    row = _pause_map(run_meta).get(str(agent_id).strip().lower())
    if not isinstance(row, dict):
        return None
    until = row.get("until")
    if not isinstance(until, (int, float)):
        return None
    base = now if now is not None else time.time()
    return float(until) if float(until) > base else None


def record_usage_limit_pause(
    agent_id: str,
    *,
    run_meta: dict[str, Any] | None,
    error: object,
    pause_seconds: float = DEFAULT_USAGE_PAUSE_SEC,
    now: float | None = None,
) -> None:
    """Mark an agent paused for this session after a confirmed usage-limit failure."""
    if not isinstance(run_meta, dict):
        return
    if not is_usage_limit_error(error):
        return
    base = now if now is not None else time.time()
    pauses = dict(_pause_map(run_meta))
    pauses[str(agent_id).strip().lower()] = {
        "until": base + pause_seconds,
        "reason": "usage_limit",
        "detail": str(error)[:240],
    }
    run_meta["_agent_pauses"] = pauses

    provider = agent_provider_id(agent_id)
    from agent_lab import usage_monitor

    usage_monitor.mark_exhausted(provider, "default", error=error, force=True, now=base)


def skip_note_for_paused_agent(agent_id: str, *, reason: str = "usage_limit") -> str:
    name = label(agent_id)  # type: ignore[arg-type]
    if reason == "usage_limit":
        return f"[{name}] 사용량 한도 도달로 이번 턴 불참합니다 (나머지 에이전트로 진행)."
    return f"[{name}] 응답 지연으로 이번 턴 불참합니다 (나머지 에이전트로 진행)."


def filter_agents_for_turn(
    agents: list[AgentId],
    *,
    run_meta: dict[str, Any] | None,
    available_fn: Callable[[], list[AgentId]] | None = None,
    now: float | None = None,
) -> list[AgentId]:
    """Drop session-paused agents; optionally fill from dynamic roster (model set unchanged)."""
    if not agents:
        return []
    _prune_expired_pauses(run_meta, now=now)
    active = [a for a in agents if agent_pause_until(run_meta, str(a), now=now) is None]
    if active:
        return active
    if not available_fn:
        return active
    from agent_lab.agent.roster import dynamic_room_enabled, resolve_active_agents

    if not dynamic_room_enabled():
        return active
    session_folder = None
    if isinstance(run_meta, dict) and run_meta.get("_session_folder"):
        from pathlib import Path

        folder = Path(str(run_meta["_session_folder"]))
        if folder.is_dir():
            session_folder = folder
    roster = resolve_active_agents(None, available_fn, session_folder=session_folder)
    return [a for a in roster if agent_pause_until(run_meta, str(a), now=now) is None]
