"""Shared agent call mocks for tests (registry.call_agent_reply)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_lab.agents.registry import AgentReply


def patch_call_agent_reply(
    monkeypatch: Any,
    handler: Callable[..., str | AgentReply],
) -> None:
    """Replace ``registry.call_agent_reply``; handler(agent, system, user, **kwargs)."""

    def _wrapper(agent: Any, system: str, user: str, **kwargs: Any) -> AgentReply:
        result = handler(agent, system, user, **kwargs)
        if isinstance(result, AgentReply):
            return result
        return AgentReply(text=str(result) if result is not None else "")

    monkeypatch.setattr("agent_lab.agents.registry.call_agent_reply", _wrapper)


def disable_execute_inbox_mcp(monkeypatch: Any) -> None:
    """Dry-run tests mock ``respond``; inbox MCP path uses ``respond_session``."""
    monkeypatch.setenv("AGENT_LAB_EXECUTE_INBOX", "0")
