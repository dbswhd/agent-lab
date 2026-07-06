"""Agent round dispatch for a single room turn (clarifier / delegate / consensus / parallel)."""

from __future__ import annotations

from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.agents.registry import AgentId
from agent_lab.run.control import RoomRunCancelled, is_cancelled
from agent_lab.room.messages import ChatMessage, OnAgentEvent


def run_turn_agent_rounds(
    *,
    topic: str,
    messages: list[ChatMessage],
    agents: list[AgentId] | None,
    clarifier_questions: list[str] | None,
    delegate_replies: list[ChatMessage] | None,
    consensus_mode: bool,
    parallel_rounds: int,
    on_event: OnAgentEvent | None,
    permissions: dict | None,
    human_turn_index: int,
    plan_md: str,
    run_meta: RunStateLike,
    context_log: list[dict[str, Any]],
    efficiency_mode: bool,
    review_mode: bool,
) -> tuple[list[ChatMessage], dict[str, Any] | None, int, bool]:
    replies: list[ChatMessage] = []
    consensus_meta: dict[str, Any] | None = None
    cancelled = False
    try:
        if clarifier_questions:
            replies = []
        elif delegate_replies is not None:
            replies = delegate_replies
            parallel_rounds = 1
        elif consensus_mode:
            room = __import__("agent_lab.room", fromlist=["run_consensus_agent_rounds"])
            replies, consensus_meta = room.run_consensus_agent_rounds(
                topic,
                messages,
                agents=agents,
                on_event=on_event,
                permissions=permissions,
                human_turn_index=human_turn_index,
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
            parallel_rounds = consensus_meta.get("rounds", 1) if consensus_meta else 1
            if consensus_meta is not None and run_meta.get("_turn_category"):
                consensus_meta.setdefault("category", run_meta.get("_turn_category"))
        else:
            room = __import__("agent_lab.room", fromlist=["run_agent_rounds"])
            replies = room.run_agent_rounds(
                topic,
                messages,
                agents=agents,
                parallel_rounds=parallel_rounds,
                on_event=on_event,
                permissions=permissions,
                review_mode=review_mode,
                human_turn_index=human_turn_index,
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
    except RoomRunCancelled:
        cancelled = True
    if cancelled or is_cancelled():
        cancelled = True
        if on_event:
            on_event("run_cancelled", {"message": "답변 중지됨"})
    return replies, consensus_meta, parallel_rounds, cancelled
