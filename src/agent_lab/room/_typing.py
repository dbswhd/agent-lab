"""Shared typing helpers for the room package."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from agent_lab.agents.registry import AgentId


def agent_label(agent: str | None) -> str:
    if not agent:
        return ""
    from agent_lab.agents.registry import AgentId as _AgentId
    from agent_lab.agents.registry import label as registry_label

    return registry_label(cast(_AgentId, agent))


def as_agent_id(agent: str) -> AgentId:
    from agent_lab.agents.registry import AgentId as _AgentId

    return cast(_AgentId, agent)


def as_agent_ids(agents: list[str]) -> list[AgentId]:
    from agent_lab.agents.registry import AgentId as _AgentId

    return cast(list[_AgentId], agents)
