"""Discuss-lane engine adapter — delegates to agents.registry (H5)."""

from __future__ import annotations

from typing import Any

from agent_lab.runtime.adapters.types import DiscussAgentId


def discuss_agent_available(agent_id: DiscussAgentId) -> bool:
    from agent_lab.agents.registry import available_agents

    return agent_id in available_agents()


def invoke_discuss(
    agent_id: DiscussAgentId,
    *,
    system: str,
    user: str,
    permissions: dict[str, Any] | None = None,
    cwd: Any = None,
    on_activity: Any = None,
    **kwargs: Any,
) -> str:
    from agent_lab.agents.registry import call_agent

    return call_agent(
        agent_id,
        system=system,
        user=user,
        permissions=permissions,
        cwd=cwd,
        on_activity=on_activity,
        **kwargs,
    )
