"""Multi-agent room: Cursor + Codex + Claude in parallel (controlled workflow).

Public facade — implementation lives in room_*.py modules.
"""

from __future__ import annotations

from agent_lab.agents.registry import (  # noqa: F401
    AGENT_IDS,
    AgentId,
    available_agents,
    call_agent,
    label,
    model_label,
)
from agent_lab.room_agent_invoke import (
    _bind_session_to_run_meta,
    _call_one_agent,
    _invoke_agent_for_round,
    _session_folder_from_run_meta,
    _set_active_turn_flags,
)
from agent_lab.room_messages import (
    ChatMessage,
    DEFAULT_AGENT_PARALLEL_ROUNDS,
    MAX_AGENT_PARALLEL_ROUNDS,
    MAX_AGENTS_PER_ROUND,
    OnAgentEvent,
    PLAN_FORMAT_VERSION,
    REVIEW_ROUND2_ORDER,
    RUN_SCHEMA_VERSION,
    _human_turn_count,
    _is_valid_synthesis,
    _round_agent_order,
    build_agent_context_bundle,
    format_thread,
)
from agent_lab.room_parallel_rounds import preview_agent_payload, run_agent_rounds, run_parallel_round
from agent_lab.room_consensus_rounds import run_consensus_agent_rounds
from agent_lab.room_plan_scribe import (
    _apply_scribe_after_turn,
    _emit_plan_actions_validation,
    _read_plan_before,
    _should_scribe_plan_after_turn,
    auto_plan_scribe_enabled,
    format_thread_numbered,
    synthesize_plan,
)
from agent_lab.room_session_persist import (
    _append_human_turn_synthesis,
    _append_peer_turn_digest,
    _session_context,
    _write_session_files,
    load_session_messages,
    save_room_session,
)
from agent_lab.room_turn_flow import continue_room_round, run_room
from agent_lab.room_turn_meta import (
    _delegate_run_meta_patch,
    consensus_reached,
    ensure_consensus_plan_sync,
    ensure_session_plan_pipeline,
    ensure_verified_plan_sync,
    maybe_auto_scribe_after_consensus,
    maybe_auto_scribe_after_verified_loop,
    synthesize_session_plan,
)

# Back-compat alias used by deps.py
room_session_context = _session_context

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
    "_append_human_turn_synthesis",
    "_append_peer_turn_digest",
    "_apply_scribe_after_turn",
    "_bind_session_to_run_meta",
    "_delegate_run_meta_patch",
    "_emit_plan_actions_validation",
    "_call_one_agent",
    "_human_turn_count",
    "_invoke_agent_for_round",
    "_is_valid_synthesis",
    "_read_plan_before",
    "_round_agent_order",
    "_session_context",
    "_session_folder_from_run_meta",
    "_set_active_turn_flags",
    "_should_scribe_plan_after_turn",
    "_write_session_files",
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
