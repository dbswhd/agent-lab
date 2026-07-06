"""agent_lab.core — dependency-zero domain types and loop-as-data (ADR §3.5 Stage 2)."""

from __future__ import annotations

from agent_lab.core.context_bundle import ContextBundle, ContextBundleMeta
from agent_lab.core.context_meta import enrich_bundle_meta, summarize_turn_context
from agent_lab.core.events import RuntimeEvent
from agent_lab.core.exceptions import ObjectionBlocksExecute, PreExecuteBlocked
from agent_lab.core.layers import Layer
from agent_lab.core.limits import agent_context_limits, trim_level
from agent_lab.core.loop_phases import TurnLoopPhase
from agent_lab.core.mission_loop import default_mission_loop, get_mission_loop
from agent_lab.core.objections import list_objections, normalize_objection
from agent_lab.core.orchestration import (
    CROSS_LANE_IMPORTS,
    FORBIDDEN_CROSS_IMPORTS,
    FORBIDDEN_EXECUTE_IMPORTS,
    CrossLaneImport,
    OrchestrationLane,
)

__all__ = [
    "ContextBundle",
    "ContextBundleMeta",
    "CROSS_LANE_IMPORTS",
    "CrossLaneImport",
    "FORBIDDEN_CROSS_IMPORTS",
    "FORBIDDEN_EXECUTE_IMPORTS",
    "Layer",
    "OrchestrationLane",
    "ObjectionBlocksExecute",
    "PreExecuteBlocked",
    "RuntimeEvent",
    "TurnLoopPhase",
    "agent_context_limits",
    "default_mission_loop",
    "enrich_bundle_meta",
    "get_mission_loop",
    "list_objections",
    "normalize_objection",
    "summarize_turn_context",
    "trim_level",
]
