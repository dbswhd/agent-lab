from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from agent_lab.agents import claude_agent, codex_agent, cursor_agent
from agent_lab.structured_envelope_adapter import merge_structured_reply

AgentId = Literal["cursor", "codex", "claude"]

AGENT_IDS: tuple[AgentId, ...] = ("cursor", "codex", "claude")

_CALLERS: dict[AgentId, Callable[..., str]] = {
    "cursor": cursor_agent.respond,
    "codex": codex_agent.respond,
    "claude": claude_agent.respond,
}

_LABELS: dict[AgentId, str] = {
    "cursor": "Cursor",
    "codex": "Codex",
    "claude": "Claude",
}


@dataclass(frozen=True)
class AgentReply:
    text: str
    structured_envelope: dict[str, Any] | None = None


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
    if os.getenv("AGENT_LAB_MOCK_STRUCTURED_ENVELOPE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        import json

        env = json.dumps({"act": "ENDORSE", "refs": [], "confidence": 0.9})
        return f"{env}\n[mock:{label(agent)}] ACK — {snippet or '(empty)'}"
    return f"[mock:{label(agent)}] ACK — {snippet or '(empty)'}"


def call_agent(
    agent: AgentId,
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    scribe: bool = False,
    on_activity: Callable[[str], None] | None = None,
    session_folder: str | Path | None = None,
) -> str:
    return call_agent_reply(
        agent,
        system,
        user,
        permissions=permissions,
        scribe=scribe,
        on_activity=on_activity,
        session_folder=session_folder,
    ).text


def call_agent_reply(
    agent: AgentId,
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    scribe: bool = False,
    on_activity: Callable[[str], None] | None = None,
    session_folder: str | Path | None = None,
    request_structured_envelope: bool = False,
) -> AgentReply:
    if _mock_agents_enabled():
        text = _mock_agent_response(agent, user, scribe=scribe)
    elif not _is_ready(agent):
        raise RuntimeError(f"{label(agent)} is not configured")
    elif agent == "cursor":
        text = cursor_agent.respond(
            system,
            user,
            permissions=permissions,
            on_activity=on_activity,
            session_folder=session_folder,
            request_structured_envelope=request_structured_envelope,
        )
    elif agent == "codex":
        text = codex_agent.respond(
            system,
            user,
            permissions=permissions,
            on_activity=on_activity,
            session_folder=session_folder,
            request_structured_envelope=request_structured_envelope,
        )
    elif agent == "claude":
        text = claude_agent.respond(
            system,
            user,
            permissions=permissions,
            scribe=scribe,
            on_activity=on_activity,
            session_folder=session_folder,
            request_structured_envelope=request_structured_envelope,
        )
    else:
        text = _CALLERS[agent](system, user)
    prose, structured = merge_structured_reply(text)
    return AgentReply(text=prose, structured_envelope=structured)
