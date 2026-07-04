from __future__ import annotations

"""Continue an existing room session turn (F9)."""

import logging
import time
from pathlib import Path
from typing import Any

from agent_lab.agents.registry import AgentId, available_agents
from agent_lab.agent.roster import resolve_active_agents
from agent_lab.attachments import describe_attachments
from agent_lab.room.agent_invoke import _bind_session_to_run_meta, _finalize_durable_turn
from agent_lab.room.messages import (
    ChatMessage,
    DEFAULT_AGENT_PARALLEL_ROUNDS,
    OnAgentEvent,
    _human_turn_count,
)
from agent_lab.room.session_persist import _session_context, load_session_messages
from agent_lab.room.turn_flow_phases import (
    build_turn_body,
    harvest_existing_session_turn,
    prepare_turn_routing_phase,
    run_consensus_phase,
)
from agent_lab.room.turn_flow_plan import (
    _casual_turn_mode,
    _post_agent_turn_plan_with_fail_banner,
)
from agent_lab.room.turn_flow_abort import _abort_mention_roster_error
from agent_lab.room.turn_flow_support import _checkpoint_chat, apply_turn_agent_mentions
from agent_lab.room.turn_meta import _delegate_run_meta_patch

import agent_lab.room.turn_flow as turn_flow

log = logging.getLogger(__name__)


def continue_room_round(
    folder: Path,
    user_message: str,
    *,
    agents: list[AgentId] | None = None,
    synthesize: bool = False,
    skill_intent: str | None = None,
    parallel_rounds: int = DEFAULT_AGENT_PARALLEL_ROUNDS,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    review_mode: bool = False,
    consensus_mode: bool = False,
    efficiency_mode: bool = False,
    turn_profile: str | None = None,
    research_mode: bool = False,
    _goal_auto_continue_depth: int = 0,
    _verified_loop_depth: int = 0,
) -> tuple[list[ChatMessage], str]:
    """Append a user turn + parallel agent replies to an existing session."""
    from agent_lab.run.control import check_cancelled

    check_cancelled()
    if not folder.is_dir():
        raise FileNotFoundError(f"session not found: {folder}")
    from agent_lab.cursor.session_metrics_mcp import ensure_session_metrics_mcp_overlays

    ensure_session_metrics_mcp_overlays(folder)
    topic_file = folder / "topic.txt"
    if topic_file.is_file():
        topic = topic_file.read_text(encoding="utf-8").strip()
    else:
        # Self-heal sessions created without a topic (e.g. a stub run.json with no
        # topic.txt/chat.jsonl): adopt this turn's message as the session topic so a
        # new turn never hard-crashes with FileNotFoundError ("Error: run failed").
        topic = user_message.strip()
        try:
            topic_file.write_text(topic, encoding="utf-8")
        except OSError:
            log.warning("failed to self-heal topic.txt for session %s", folder, exc_info=True)
    messages = load_session_messages(folder)
    user_text = user_message.strip()
    att = describe_attachments(folder)
    human_turn_index = _human_turn_count(messages)
    human_turn_num = _human_turn_count(messages) + 1
    plan_md, run_meta = _session_context(folder)
    efficiency_mode = efficiency_mode or bool((run_meta or {}).get("adaptive_efficiency"))
    from agent_lab.inbox.harvest import clear_inbox_fork_grace

    clear_inbox_fork_grace(run_meta)
    _bind_session_to_run_meta(run_meta, folder)
    requested_agents = resolve_active_agents(agents, available_agents, session_folder=folder)
    from agent_lab.agent.availability import filter_agents_for_turn

    active_agents = filter_agents_for_turn(
        requested_agents,
        run_meta=run_meta,
        available_fn=available_agents,
    )

    user_text, active_agents, mention_targets, mention_error = apply_turn_agent_mentions(
        user_text,
        active_agents,
        run_meta,
        roster_pool=requested_agents,
    )
    body = build_turn_body(user_text, att)
    messages.append(ChatMessage(role="user", agent=None, content=body))
    _checkpoint_chat(folder, messages, topic=topic)
    from agent_lab.trace_recorder import install_tracer

    on_event = install_tracer(folder, run_meta, on_event, human_turn=human_turn_num)
    if mention_error:
        mode = _casual_turn_mode(synthesize)
        return _abort_mention_roster_error(
            folder,
            topic=topic,
            messages=messages,
            plan_md=plan_md,
            run_meta=run_meta,
            active_agents=active_agents,
            mode=mode,
            synthesize=synthesize,
            on_event=on_event,
            message=mention_error,
            permissions=permissions,
            turn_profile=turn_profile,
        )
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, agents=[str(a) for a in active_agents])
    routing = prepare_turn_routing_phase(
        folder=folder,
        run_meta=run_meta,
        plan_md=plan_md,
        body=body,
        active_agents=active_agents,
        mention_targets=mention_targets,
        synthesize=synthesize,
        skill_intent=skill_intent,
        consensus_mode=consensus_mode,
        parallel_rounds=parallel_rounds,
        turn_profile=turn_profile,
        review_mode=review_mode,
        human_turn_index=human_turn_index,
        human_turn_num=human_turn_num,
        efficiency_mode=efficiency_mode,
        research_mode=research_mode,
        on_event=on_event,
        is_new_session=False,
        begin_human_turn_hooks=True,
    )
    run_meta = routing.run_meta
    plan_md = routing.plan_md
    mode = routing.mode
    review_advocate = routing.review_advocate
    consensus_mode = routing.consensus_mode
    parallel_rounds = routing.parallel_rounds
    efficiency_mode = routing.efficiency_mode
    clarifier_questions = routing.clarifier_questions
    t0 = time.perf_counter()
    context_log: list[dict[str, Any]] = []
    plan_before = (folder / "plan.md").read_text(encoding="utf-8") if (folder / "plan.md").is_file() else ""
    consensus = run_consensus_phase(
        topic=topic,
        messages=messages,
        folder=folder,
        body=body,
        run_meta=run_meta,
        active_agents=active_agents,
        clarifier_questions=clarifier_questions,
        consensus_mode=consensus_mode,
        parallel_rounds=parallel_rounds,
        on_event=on_event,
        permissions=permissions,
        human_turn_index=human_turn_index,
        human_turn_num=human_turn_num,
        plan_md=plan_md,
        context_log=context_log,
        efficiency_mode=efficiency_mode,
        review_mode=review_mode,
        mode=mode,
        synthesize=synthesize,
    )
    return harvest_existing_session_turn(
        folder,
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        plan_before=plan_before,
        mode=mode,
        synthesize=synthesize,
        cancelled=consensus.cancelled,
        active_agents=active_agents,
        permissions=permissions,
        on_event=on_event,
        consensus_meta=consensus.consensus_meta,
        consensus_mode=consensus_mode,
        human_turn_num=human_turn_num,
        turn_profile=turn_profile,
        review_mode=review_mode,
        review_advocate=review_advocate,
        parallel_rounds=consensus.parallel_rounds,
        context_log=context_log,
        efficiency_mode=efficiency_mode,
        research_mode=research_mode,
        clarifier_questions=clarifier_questions,
        replies=consensus.replies,
        t0=t0,
        post_agent_turn_plan=_post_agent_turn_plan_with_fail_banner,
        finalize_durable_turn=_finalize_durable_turn,
        delegate_run_meta_patch=_delegate_run_meta_patch,
        continue_round=turn_flow.continue_room_round,
        _goal_auto_continue_depth=_goal_auto_continue_depth,
        _verified_loop_depth=_verified_loop_depth,
        merge_meta_extra={"topic": topic},
    )
