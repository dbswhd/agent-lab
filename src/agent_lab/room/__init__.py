"""Multi-agent room: Cursor + Codex + Claude in parallel (controlled workflow).

Public facade — submodules under ``agent_lab.room.*``.
Imports are lazy so ``import agent_lab.room.sse_stream`` does not load the full facade.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "AGENT_IDS",
    "AgentId",
    "ChatMessage",
    "DEFAULT_AGENT_PARALLEL_ROUNDS",
    "MAX_AGENT_PARALLEL_ROUNDS",
    "MAX_AGENTS_PER_ROUND",
    "OnAgentEvent",
    "PLAN_FORMAT_VERSION",
    "REVIEW_ROUND2_ORDER",
    "RUN_SCHEMA_VERSION",
    "auto_plan_scribe_enabled",
    "available_agents",
    "build_agent_context_bundle",
    "call_agent",
    "consensus_reached",
    "continue_room_round",
    "ensure_consensus_plan_sync",
    "ensure_session_plan_pipeline",
    "ensure_verified_plan_sync",
    "format_thread",
    "format_thread_numbered",
    "label",
    "load_session_messages",
    "model_label",
    "maybe_auto_scribe_after_consensus",
    "maybe_auto_scribe_after_verified_loop",
    "preview_agent_payload",
    "room_session_context",
    "run_agent_rounds",
    "run_consensus_agent_rounds",
    "run_parallel_round",
    "run_room",
    "save_room_session",
    "synthesize_plan",
    "synthesize_session_plan",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "AGENT_IDS": ("agent_lab.agents.registry", "AGENT_IDS"),
    "AgentId": ("agent_lab.agents.registry", "AgentId"),
    "available_agents": ("agent_lab.agents.registry", "available_agents"),
    "call_agent": ("agent_lab.agents.registry", "call_agent"),
    "label": ("agent_lab.agents.registry", "label"),
    "model_label": ("agent_lab.agents.registry", "model_label"),
    "ChatMessage": ("agent_lab.room.messages", "ChatMessage"),
    "DEFAULT_AGENT_PARALLEL_ROUNDS": ("agent_lab.room.messages", "DEFAULT_AGENT_PARALLEL_ROUNDS"),
    "MAX_AGENT_PARALLEL_ROUNDS": ("agent_lab.room.messages", "MAX_AGENT_PARALLEL_ROUNDS"),
    "MAX_AGENTS_PER_ROUND": ("agent_lab.room.messages", "MAX_AGENTS_PER_ROUND"),
    "OnAgentEvent": ("agent_lab.room.messages", "OnAgentEvent"),
    "PLAN_FORMAT_VERSION": ("agent_lab.room.messages", "PLAN_FORMAT_VERSION"),
    "REVIEW_ROUND2_ORDER": ("agent_lab.room.messages", "REVIEW_ROUND2_ORDER"),
    "RUN_SCHEMA_VERSION": ("agent_lab.room.messages", "RUN_SCHEMA_VERSION"),
    "build_agent_context_bundle": ("agent_lab.room.messages", "build_agent_context_bundle"),
    "format_thread": ("agent_lab.room.messages", "format_thread"),
    "preview_agent_payload": ("agent_lab.room.parallel_rounds", "preview_agent_payload"),
    "run_agent_rounds": ("agent_lab.room.parallel_rounds", "run_agent_rounds"),
    "run_parallel_round": ("agent_lab.room.parallel_rounds", "run_parallel_round"),
    "run_consensus_agent_rounds": ("agent_lab.room.consensus_rounds", "run_consensus_agent_rounds"),
    "auto_plan_scribe_enabled": ("agent_lab.room.plan_scribe", "auto_plan_scribe_enabled"),
    "format_thread_numbered": ("agent_lab.room.plan_scribe", "format_thread_numbered"),
    "synthesize_plan": ("agent_lab.room.plan_scribe", "synthesize_plan"),
    "load_session_messages": ("agent_lab.room.session_persist", "load_session_messages"),
    "save_room_session": ("agent_lab.room.session_persist", "save_room_session"),
    "room_session_context": ("agent_lab.room.session_persist", "_session_context"),
    "continue_room_round": ("agent_lab.room.turn_flow", "continue_room_round"),
    "run_room": ("agent_lab.room.turn_flow", "run_room"),
    "consensus_reached": ("agent_lab.room.turn_meta", "consensus_reached"),
    "ensure_consensus_plan_sync": ("agent_lab.room.turn_meta", "ensure_consensus_plan_sync"),
    "ensure_session_plan_pipeline": ("agent_lab.room.turn_meta", "ensure_session_plan_pipeline"),
    "ensure_verified_plan_sync": ("agent_lab.room.turn_meta", "ensure_verified_plan_sync"),
    "maybe_auto_scribe_after_consensus": ("agent_lab.room.turn_meta", "maybe_auto_scribe_after_consensus"),
    "maybe_auto_scribe_after_verified_loop": ("agent_lab.room.turn_meta", "maybe_auto_scribe_after_verified_loop"),
    "synthesize_session_plan": ("agent_lab.room.turn_meta", "synthesize_session_plan"),
}


def __getattr__(name: str) -> Any:
    spec = _EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod_name, attr = spec
    return getattr(importlib.import_module(mod_name), attr)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
