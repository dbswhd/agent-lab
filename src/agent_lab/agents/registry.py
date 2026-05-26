from __future__ import annotations

import os
from typing import Any, Callable, Literal

from agent_lab.agents import claude_agent, codex_agent, cursor_agent

AgentId = Literal["cursor", "codex", "claude"]

AGENT_IDS: tuple[AgentId, ...] = ("cursor", "codex", "claude")

_CALLERS: dict[AgentId, Callable[[str, str], str]] = {
    "cursor": cursor_agent.respond,
    "codex": codex_agent.respond,
    "claude": claude_agent.respond,
}

_LABELS: dict[AgentId, str] = {
    "cursor": "Cursor",
    "codex": "Codex",
    "claude": "Claude",
}


def label(agent: AgentId) -> str:
    return _LABELS[agent]


def available_agents() -> list[AgentId]:
    out: list[AgentId] = []
    for aid in AGENT_IDS:
        try:
            if _is_ready(aid):
                out.append(aid)
        except Exception:
            continue
    return out


def _is_ready(agent: AgentId) -> bool:
    if agent == "codex":
        from agent_lab import codex_cli

        return codex_cli.is_available()
    if agent == "claude":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    if agent == "cursor":
        return cursor_agent.is_available()
    return False


def call_agent(
    agent: AgentId,
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
) -> str:
    if not _is_ready(agent):
        raise RuntimeError(f"{label(agent)} is not configured")
    if agent == "cursor":
        return cursor_agent.respond(system, user, permissions=permissions)
    return _CALLERS[agent](system, user)
