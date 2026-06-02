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


def model_label(agent: AgentId) -> str:
    if agent == "codex":
        from agent_lab import codex_cli

        return codex_cli.model_label()
    if agent == "claude":
        from agent_lab import claude_cli

        return claude_cli.model_label()
    if agent == "cursor":
        return cursor_agent.model_label()
    return ""


def available_agents() -> list[AgentId]:
    if _mock_agents_enabled():
        return list(AGENT_IDS)
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
        from agent_lab import claude_cli

        return claude_cli.is_available()
    if agent == "cursor":
        return cursor_agent.is_available()
    return False


def _mock_agents_enabled() -> bool:
    return os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _mock_agent_response(
    agent: AgentId,
    user: str,
    *,
    scribe: bool = False,
) -> str:
    if scribe:
        return "## Mock plan\n\n- mock scribe turn\n"
    snippet = " ".join(user.strip().split())[:100]
    return f"[mock:{label(agent)}] ACK — {snippet or '(empty)'}"


def call_agent(
    agent: AgentId,
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    scribe: bool = False,
    on_activity: Callable[[str], None] | None = None,
) -> str:
    if _mock_agents_enabled():
        return _mock_agent_response(agent, user, scribe=scribe)
    if not _is_ready(agent):
        raise RuntimeError(f"{label(agent)} is not configured")
    if agent == "cursor":
        return cursor_agent.respond(
            system, user, permissions=permissions, on_activity=on_activity
        )
    if agent == "codex":
        return codex_agent.respond(
            system, user, permissions=permissions, on_activity=on_activity
        )
    if agent == "claude":
        return claude_agent.respond(system, user, permissions=permissions, scribe=scribe)
    return _CALLERS[agent](system, user)
