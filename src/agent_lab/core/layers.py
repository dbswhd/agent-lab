"""Orchestration layer names for import-cycle guards."""

from __future__ import annotations

from enum import StrEnum


class Layer(StrEnum):
    """Top-level agent_lab packages participating in orchestration DAG."""

    CORE = "core"
    RUNTIME = "runtime"
    ROOM = "room"
    PLAN = "plan"
    MISSION = "mission"
    RUN = "run"
    SESSION = "session"
    INBOX = "inbox"
    CONTEXT = "context"
    AGENT = "agent"
    WORKSPACE = "workspace"
    OTHER = "other"


ORCHESTRATION_LAYERS: frozenset[Layer] = frozenset(
    {
        Layer.CORE,
        Layer.RUNTIME,
        Layer.ROOM,
        Layer.PLAN,
        Layer.MISSION,
        Layer.RUN,
        Layer.SESSION,
        Layer.INBOX,
        Layer.CONTEXT,
    }
)


def layer_for_module(module: str) -> Layer:
    """Map ``agent_lab.<pkg>...`` to a :class:`Layer`."""
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "agent_lab":
        return Layer.OTHER
    try:
        return Layer(parts[1])
    except ValueError:
        return Layer.OTHER
