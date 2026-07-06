from __future__ import annotations

"""Start or resume a full room session turn (F9)."""

import logging
import time
from pathlib import Path
from typing import Any

from agent_lab.agents.registry import AgentId
from agent_lab.room.agent_invoke import _finalize_durable_turn
from agent_lab.room.messages import (
    ChatMessage,
    DEFAULT_AGENT_PARALLEL_ROUNDS,
    OnAgentEvent,
)
from agent_lab.room.plan_scribe import _read_plan_before
from agent_lab.room.turn_flow_phases import (
    harvest_existing_session_turn,
    harvest_new_session_turn,
    prepare_run_room_start,
    prepare_turn_routing_phase,
    run_consensus_phase,
)
from agent_lab.room.turn_flow_plan import _post_agent_turn_plan_with_fail_banner
from agent_lab.room.turn_meta import _delegate_run_meta_patch

import agent_lab.room.turn_flow as turn_flow

log = logging.getLogger(__name__)


def run_room(
    topic: str,
    *,
    agents: list[AgentId] | None = None,
    synthesize: bool = True,
    skill_intent: str | None = None,
    parallel_rounds: int = DEFAULT_AGENT_PARALLEL_ROUNDS,
    on_event: OnAgentEvent | None = None,
    sessions_base: Path | None = None,
    session_folder: Path | None = None,
    permissions: dict | None = None,
    review_mode: bool = False,
    consensus_mode: bool = False,
    efficiency_mode: bool = False,
    turn_profile: str | None = None,
    research_mode: bool = False,
) -> tuple[Path, list[ChatMessage], str]:
    """Full room flow: user message → parallel agents → optional plan synthesis."""
    from agent_lab.run.control import check_cancelled

    check_cancelled()
    start = prepare_run_room_start(
        topic,
        agents=agents,
        synthesize=synthesize,
        sessions_base=sessions_base,
        session_folder=session_folder,
        permissions=permissions,
        turn_profile=turn_profile,
        on_event=on_event,
    )
    if start.abort is not None:
        return start.abort

    routing = prepare_turn_routing_phase(
        folder=start.folder,
        run_meta=start.run_meta,
        plan_md=start.plan_md,
        body=start.body,
        active_agents=start.active_agents,
        mention_targets=start.mention_targets,
        synthesize=start.synthesize,
        skill_intent=skill_intent,
        consensus_mode=consensus_mode,
        parallel_rounds=parallel_rounds,
        turn_profile=turn_profile,
        review_mode=review_mode,
        human_turn_index=start.human_turn_index,
        human_turn_num=start.human_turn_num,
        efficiency_mode=efficiency_mode,
        research_mode=research_mode,
        on_event=start.on_event,
        is_new_session=start.is_new,
        begin_human_turn_hooks=False,
    )
    t0 = time.perf_counter()
    context_log: list[dict[str, Any]] = []
    consensus = run_consensus_phase(
        topic=start.topic,
        messages=start.messages,
        folder=start.folder,
        body=start.body,
        run_meta=routing.run_meta,
        active_agents=start.active_agents,
        clarifier_questions=routing.clarifier_questions,
        consensus_mode=routing.consensus_mode,
        parallel_rounds=routing.parallel_rounds,
        on_event=start.on_event,
        permissions=start.permissions,
        human_turn_index=start.human_turn_index,
        human_turn_num=start.human_turn_num,
        plan_md=routing.plan_md,
        context_log=context_log,
        efficiency_mode=routing.efficiency_mode,
        review_mode=review_mode,
        mode=routing.mode,
        synthesize=start.synthesize,
    )

    if start.folder is not None:
        plan_before = _read_plan_before(start.folder)
        messages, plan_md = harvest_existing_session_turn(
            start.folder,
            topic=start.topic,
            messages=start.messages,
            run_meta=routing.run_meta,
            plan_before=plan_before,
            mode=routing.mode,
            synthesize=start.synthesize,
            cancelled=consensus.cancelled,
            active_agents=start.active_agents,
            permissions=start.permissions,
            on_event=start.on_event,
            consensus_meta=consensus.consensus_meta,
            consensus_mode=routing.consensus_mode,
            human_turn_num=start.human_turn_num,
            turn_profile=turn_profile,
            review_mode=review_mode,
            review_advocate=routing.review_advocate,
            parallel_rounds=consensus.parallel_rounds,
            context_log=context_log,
            efficiency_mode=routing.efficiency_mode,
            research_mode=research_mode,
            clarifier_questions=routing.clarifier_questions,
            replies=consensus.replies,
            t0=t0,
            post_agent_turn_plan=_post_agent_turn_plan_with_fail_banner,
            finalize_durable_turn=_finalize_durable_turn,
            delegate_run_meta_patch=_delegate_run_meta_patch,
            continue_round=turn_flow.continue_room_round,
        )
        return start.folder, messages, plan_md

    return harvest_new_session_turn(
        topic=start.topic,
        messages=start.messages,
        run_meta=routing.run_meta,
        active_agents=start.active_agents,
        mode=routing.mode,
        synthesize=start.synthesize,
        cancelled=consensus.cancelled,
        on_event=start.on_event,
        consensus_meta=consensus.consensus_meta,
        consensus_mode=routing.consensus_mode,
        parallel_rounds=consensus.parallel_rounds,
        permissions=start.permissions,
        turn_profile=turn_profile,
        review_mode=review_mode,
        review_advocate=routing.review_advocate,
        context_log=context_log,
        efficiency_mode=routing.efficiency_mode,
        clarifier_questions=routing.clarifier_questions,
        replies=consensus.replies,
        t0=t0,
        sessions_base=start.sessions_base,
        finalize_durable_turn=_finalize_durable_turn,
    )
