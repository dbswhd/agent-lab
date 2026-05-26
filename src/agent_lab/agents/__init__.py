"""Platform agents: Cursor, Codex, Claude."""

from agent_lab.agents.registry import (
    AGENT_IDS,
    AgentId,
    available_agents,
    call_agent,
)

__all__ = ["AGENT_IDS", "AgentId", "available_agents", "call_agent"]
