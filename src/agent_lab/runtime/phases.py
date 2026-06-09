"""Session phase and mode vocabulary for the unified runtime harness (H0)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

# Mirrors mission_loop.MissionPhase — keep in sync until H1 runtime owns phase writes.
MissionPhase = Literal[
    "MISSION_DEFINE",
    "MISSION_PAUSED",
    "DISCUSS",
    "PLAN_GATE",
    "PLAN_REJECT",
    "EXECUTE_QUEUE",
    "DRY_RUN",
    "MERGE_REVIEW",
    "VERIFY",
    "REPAIR",
    "MISSION_DONE",
]

MISSION_PHASES: frozenset[str] = frozenset(
    {
        "MISSION_DEFINE",
        "MISSION_PAUSED",
        "DISCUSS",
        "PLAN_GATE",
        "PLAN_REJECT",
        "EXECUTE_QUEUE",
        "DRY_RUN",
        "MERGE_REVIEW",
        "VERIFY",
        "REPAIR",
        "MISSION_DONE",
    }
)


class SessionMode(StrEnum):
    """How a session runs when mission_loop.enabled is false vs true."""

    STANDALONE = "standalone"
    """Room + manual execute; no mission FSM phase writes."""

    MISSION = "mission"
    """mission_loop.enabled — conductor FSM drives discuss ↔ execute ↔ verify."""
