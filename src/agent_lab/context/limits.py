"""Central context budget limits — re-export from core (F12)."""

from __future__ import annotations

from typing import Any

from agent_lab.core.limits import (  # noqa: F401
    AgentContextLimits,
    EfficiencyLimits,
    ScribeContextLimits,
    agent_context_limits,
    efficiency_limits,
    efficiency_mode_default,
    scribe_context_limits,
    trim_level,
)

__all__ = [
    "AgentContextLimits",
    "EfficiencyLimits",
    "ScribeContextLimits",
    "agent_context_limits",
    "all_limits_for_api",
    "efficiency_limits",
    "efficiency_mode_default",
    "scribe_context_limits",
    "trim_level",
]


def all_limits_for_api() -> dict[str, Any]:
    from agent_lab.room.consensus import max_consensus_calls, max_consensus_rounds

    return {
        "agent": agent_context_limits().to_dict(),
        "scribe": scribe_context_limits().to_dict(),
        "consensus": {
            "max_rounds": max_consensus_rounds(),
            "max_calls": max_consensus_calls(),
        },
        "efficiency": efficiency_limits().to_dict(),
    }
