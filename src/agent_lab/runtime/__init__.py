"""Unified runtime harness — H0 contract (phases, events, transitions, import graph).

Implementation of ``AgentLabRuntime.dispatch`` is Phase H1+; this package holds
the orchestration contract extracted from ``room.py``, ``mission_loop.py``, and
``plan_execute.py``.
"""

from __future__ import annotations

from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.import_graph import CROSS_LANE_IMPORTS, OrchestrationLane
from agent_lab.runtime.phases import MissionPhase, SessionMode
from agent_lab.runtime.context import build_mission_wisdom_block, enrich_execute_prompt
from agent_lab.runtime.policy import PolicyEngine, PolicyResult
from agent_lab.runtime.dispatch_result import DispatchResult
from agent_lab.runtime.runtime import dispatch, dispatch_verify_result
from agent_lab.runtime.boulder import (
    boulder_state,
    clear_boulder,
    clear_last_failure,
    last_failure,
    record_last_failure,
    sync_boulder,
    sync_boulder_from_partial,
)
from agent_lab.runtime.snapshot import build_runtime_snapshot, public_runtime_payload
from agent_lab.runtime.transitions import RuntimeTransition, TRANSITION_TABLE
from agent_lab.runtime.work_phase import WorkPhase, resolve_work_phase

__all__ = [
    "CROSS_LANE_IMPORTS",
    "DispatchResult",
    "MissionPhase",
    "OrchestrationLane",
    "RuntimeEvent",
    "RuntimeTransition",
    "TRANSITION_TABLE",
    "SessionMode",
    "WorkPhase",
    "boulder_state",
    "build_runtime_snapshot",
    "clear_boulder",
    "clear_last_failure",
    "last_failure",
    "PolicyEngine",
    "PolicyResult",
    "build_mission_wisdom_block",
    "dispatch",
    "dispatch_verify_result",
    "enrich_execute_prompt",
    "public_runtime_payload",
    "record_last_failure",
    "resolve_work_phase",
    "sync_boulder",
    "sync_boulder_from_partial",
]
