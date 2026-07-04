"""Top-level run_room and continue_room_round entry points."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _casual_turn_mode(synthesize: bool) -> str:
    from agent_lab.room.turn_policy import turn_policy_enabled

    if turn_policy_enabled():
        return "discuss"
    return "plan" if synthesize else "discuss"


from agent_lab.agents.registry import AgentId, available_agents
from agent_lab.agent.roster import resolve_active_agents
from agent_lab.attachments import describe_attachments
from agent_lab.run.control import check_cancelled
from agent_lab.room.messages import (
    ChatMessage,
    DEFAULT_AGENT_PARALLEL_ROUNDS,
    OnAgentEvent,
    _agent_turn_summary,
    _emit_turn_terminal_status,
    _human_turn_count,
    _turn_status_from_replies,
)
from agent_lab.room.agent_invoke import (
    _bind_session_to_run_meta,
    _finalize_durable_turn,
)


from agent_lab.room.plan_scribe import (
    _apply_scribe_after_turn,
    _bootstrap_session_folder_for_plan_workflow,
    _plan_trigger_for_turn,
    _plan_workflow_post_agent_turn,
    _read_plan_before,
    _should_scribe_plan_after_turn,
)

from agent_lab.room.session_persist import (
    _session_context,
    _write_session_files,
    load_session_messages,
    save_room_session,
)

from agent_lab.room.turn_meta import (
    _delegate_run_meta_patch,
    _peer_metrics_for_messages,
    _turn_snapshot,
)


from agent_lab.room.turn_flow_finalize import emit_turn_complete_event
from agent_lab.room.turn_flow_phases import (
    build_turn_body,
    harvest_existing_session_turn,
    prepare_turn_routing_phase,
    run_consensus_phase,
)
from agent_lab.room.turn_flow_support import (
    _checkpoint_chat,
    _emit_budget_status,
    _emit_divergence_options,
    _resolve_stage_routing,
    _session_hard_cap_enabled,
    apply_turn_agent_mentions,
)


def _post_agent_turn_plan(
    folder: Path,
    *,
    topic: str,
    messages: list[ChatMessage],
    run_meta: dict[str, Any],
    plan_before: str,
    mode: str,
    synthesize: bool,
    cancelled: bool,
    active_agents: list[Any],
    permissions: dict | None,
    on_event: OnAgentEvent | None,
    consensus_meta: dict[str, Any] | None,
    human_turn_num: int,
) -> tuple[str, bool, dict[str, Any], str | None]:
    from agent_lab.room.turn_policy import (
        TurnSignals,
        apply_turn_effects,
        count_proposed_tags_in_turn,
        turn_policy_enabled,
    )

    if turn_policy_enabled():
        result = apply_turn_effects(
            signals=TurnSignals.from_run_meta(
                run_meta,
                consensus_meta=consensus_meta,
                cancelled=cancelled,
                proposed_tags_count=count_proposed_tags_in_turn(messages),
            ),
            folder=folder,
            topic=topic,
            messages=messages,
            run_meta=run_meta,
            plan_before=plan_before,
            mode=mode,
            cancelled=cancelled,
            active_agents=active_agents,
            permissions=permissions,
            on_event=on_event,
            consensus_meta=consensus_meta,
            human_turn=human_turn_num,
        )
        return result.plan_md, result.scribe_applied, result.run_meta, result.plan_trigger

    plan_md, scribe_applied, run_meta = _plan_workflow_post_agent_turn(
        folder,
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        plan_before=plan_before,
        mode=mode,
        synthesize=synthesize,
        cancelled=cancelled,
        active_agents=active_agents,
        permissions=permissions,
        on_event=on_event,
    )
    plan_trigger = _plan_trigger_for_turn(synthesize=synthesize, scribe_applied=scribe_applied)
    return plan_md, scribe_applied, run_meta, plan_trigger


def _post_agent_turn_plan_with_fail_banner(
    folder: Path,
    *,
    topic: str,
    messages: list[ChatMessage],
    run_meta: dict[str, Any],
    plan_before: str,
    mode: str,
    synthesize: bool,
    cancelled: bool,
    active_agents: list[Any],
    permissions: dict | None,
    on_event: OnAgentEvent | None,
    consensus_meta: dict[str, Any] | None,
    human_turn_num: int,
) -> tuple[str, bool, dict[str, Any], str | None]:
    plan_md, scribe_applied, run_meta, plan_trigger = _post_agent_turn_plan(
        folder,
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        plan_before=plan_before,
        mode=mode,
        synthesize=synthesize,
        cancelled=cancelled,
        active_agents=active_agents,
        permissions=permissions,
        on_event=on_event,
        consensus_meta=consensus_meta,
        human_turn_num=human_turn_num,
    )
    if synthesize and scribe_applied and not plan_md:
        plan_md = "## Plan synthesis failed\n\nunknown error"
    return plan_md, scribe_applied, run_meta, plan_trigger


def _abort_mention_roster_error(
    folder: Path | None,
    *,
    topic: str,
    messages: list[ChatMessage],
    plan_md: str,
    run_meta: dict[str, Any],
    active_agents: list[Any],
    mode: str,
    synthesize: bool,
    on_event: OnAgentEvent | None,
    message: str,
    permissions: dict | None,
    turn_profile: str | None,
) -> tuple[list[ChatMessage], str]:
    """Persist a failed turn when explicit @-mentions are outside the session roster."""
    from agent_lab.room.turn_flow_support import emit_mention_roster_error

    emit_mention_roster_error(on_event, message)
    messages.append(
        ChatMessage(role="system", agent=None, content=message, visibility="human"),
    )
    _checkpoint_chat(folder, messages, topic=topic)
    if folder is not None and folder.is_dir():
        _write_session_files(
            folder,
            topic,
            messages,
            plan_md,
            agents_used=[str(a) for a in active_agents],
            merge_meta={"topic": topic},
            turn_meta=_turn_snapshot(
                mode=mode,
                synthesize=synthesize,
                agents_used=[str(a) for a in active_agents],
                parallel_rounds=0,
                permissions=permissions,
                latency_ms=0,
                status="failed",
                turn_profile=turn_profile,
                failed_agents=[],
                succeeded_agents=[],
            ),
            run_meta_patch=_delegate_run_meta_patch(run_meta),
        )
    return messages, plan_md


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
        continue_round=continue_room_round,
        _goal_auto_continue_depth=_goal_auto_continue_depth,
        _verified_loop_depth=_verified_loop_depth,
        merge_meta_extra={"topic": topic},
    )


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
    from agent_lab.agent.permissions import normalize_agent_permissions
    from agent_lab.run.control import check_cancelled

    check_cancelled()
    permissions = normalize_agent_permissions(permissions)
    user_text = topic.strip()
    att = ""
    if session_folder and session_folder.is_dir():
        att = describe_attachments(session_folder)
    folder: Path | None = None
    if session_folder and session_folder.is_dir():
        folder = session_folder
        if (folder / "topic.txt").is_file():
            topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()

    plan_md, run_meta = _session_context(folder)
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
    messages: list[ChatMessage] = [ChatMessage(role="user", agent=None, content=body)]
    if folder is not None:
        messages = load_session_messages(folder) + messages
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, agents=[str(a) for a in active_agents])
    human_turn_index = _human_turn_count(messages) - 1
    mode = _casual_turn_mode(synthesize)
    human_turn_num = max(1, _human_turn_count(messages))
    if folder is None and synthesize:
        boot = _bootstrap_session_folder_for_plan_workflow(
            topic,
            base=sessions_base,
            synthesize=synthesize,
        )
        if boot is not None:
            folder = boot
            plan_md, run_meta = _session_context(folder)
            _bind_session_to_run_meta(run_meta, folder)
    _checkpoint_chat(folder, messages, topic=topic)
    from agent_lab.trace_recorder import install_tracer

    on_event = install_tracer(folder, run_meta, on_event, human_turn=human_turn_num)
    if mention_error:
        abort_messages, abort_plan_md = _abort_mention_roster_error(
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
        if folder is None:
            raise RuntimeError("mention roster error before session folder exists")
        return folder, abort_messages, abort_plan_md
    is_new = folder is None or not (folder / "chat.jsonl").is_file()
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
        human_turn_index=max(0, human_turn_index),
        human_turn_num=human_turn_num,
        efficiency_mode=efficiency_mode,
        research_mode=research_mode,
        on_event=on_event,
        is_new_session=is_new,
        begin_human_turn_hooks=False,
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
        human_turn_index=max(0, human_turn_index),
        human_turn_num=human_turn_num,
        plan_md=plan_md,
        context_log=context_log,
        efficiency_mode=efficiency_mode,
        review_mode=review_mode,
        mode=mode,
        synthesize=synthesize,
    )
    cancelled = consensus.cancelled
    replies = consensus.replies
    consensus_meta = consensus.consensus_meta
    parallel_rounds = consensus.parallel_rounds

    if folder is not None:
        plan_before = _read_plan_before(folder)
        messages, plan_md = harvest_existing_session_turn(
            folder,
            topic=topic,
            messages=messages,
            run_meta=run_meta,
            plan_before=plan_before,
            mode=mode,
            synthesize=synthesize,
            cancelled=cancelled,
            active_agents=active_agents,
            permissions=permissions,
            on_event=on_event,
            consensus_meta=consensus_meta,
            consensus_mode=consensus_mode,
            human_turn_num=human_turn_num,
            turn_profile=turn_profile,
            review_mode=review_mode,
            review_advocate=review_advocate,
            parallel_rounds=parallel_rounds,
            context_log=context_log,
            efficiency_mode=efficiency_mode,
            research_mode=research_mode,
            clarifier_questions=clarifier_questions,
            replies=replies,
            t0=t0,
            post_agent_turn_plan=_post_agent_turn_plan_with_fail_banner,
            finalize_durable_turn=_finalize_durable_turn,
            delegate_run_meta_patch=_delegate_run_meta_patch,
            continue_round=continue_room_round,
        )
        return folder, messages, plan_md

    plan_before = ""
    plan_md = plan_before
    scribe_applied = _should_scribe_plan_after_turn(synthesize=synthesize, cancelled=cancelled)
    plan_trigger = None
    if scribe_applied:
        plan_md = _apply_scribe_after_turn(
            topic=topic,
            messages=messages,
            run_meta=run_meta,
            plan_before=plan_before,
            mode=mode,
            scribe=True,
            user_plan_send=synthesize,
            cancelled=cancelled,
            on_event=on_event,
            session_folder=folder,
            plan_trigger="plan_turn" if synthesize else "auto_turn",
        )
        plan_trigger = "plan_turn" if synthesize else "auto_turn"
        if synthesize and not plan_md:
            plan_md = "## Plan synthesis failed\n\nunknown error"
    else:
        plan_trigger = _plan_trigger_for_turn(synthesize=synthesize, scribe_applied=False)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    turn_summary = _agent_turn_summary(replies)
    turn_status = _turn_status_from_replies(
        replies,
        cancelled=cancelled,
        consensus_meta=consensus_meta,
        consensus_mode=consensus_mode,
    )
    _emit_turn_terminal_status(
        status=turn_status,
        replies=replies,
        on_event=on_event,
        consensus_mode=consensus_mode,
    )
    from agent_lab.room.team_orchestration import resolve_send_receipt

    peer = _peer_metrics_for_messages(messages)
    send_receipt_val = resolve_send_receipt(
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
        consensus=consensus_meta,
        plan_updated=bool(scribe_applied and not cancelled and plan_md and plan_md != plan_before),
        status=turn_status,
        plan_workflow_phase=None,
        turn_policy=run_meta.get("turn_policy") if isinstance(run_meta.get("turn_policy"), dict) else None,
        turn_kind=str(run_meta.get("turn_kind") or "") or None,
    )
    from agent_lab.room.turn_flow_phases import compose_turn_meta

    turn_meta = compose_turn_meta(
        mode=mode,
        synthesize=synthesize,
        active_agents=active_agents,
        parallel_rounds=parallel_rounds,
        permissions=permissions,
        latency_ms=latency_ms,
        turn_status=turn_status,
        review_mode=review_mode,
        review_advocate=review_advocate,
        context_log=context_log,
        consensus_mode=consensus_mode,
        consensus_meta=consensus_meta,
        efficiency_mode=efficiency_mode,
        messages=messages,
        run_meta=run_meta,
        plan_md=plan_md,
        turn_profile=turn_profile,
        send_receipt_val=send_receipt_val,
        turn_summary=turn_summary,
        plan_trigger=plan_trigger,
        peer=peer,
        replies=replies,
    )

    from agent_lab.plan.workflow import init_plan_workflow_on_plan_send, should_enable_plan_workflow
    from agent_lab.room.turn_policy import turn_policy_enabled

    folder = save_room_session(
        topic,
        messages,
        plan_md,
        base=sessions_base,
        agents_used=active_agents,
        turn_meta=turn_meta,
        clarifier_questions=clarifier_questions,
    )
    if not turn_policy_enabled() and should_enable_plan_workflow(synthesize=synthesize):
        init_plan_workflow_on_plan_send(folder)
    _finalize_durable_turn(folder, 1, turn_status)
    emit_turn_complete_event(
        folder,
        on_event=on_event,
        cancelled=cancelled,
        turn_status=turn_status,
        turn_summary=turn_summary,
        send_receipt_val=send_receipt_val,
        verified_result=None,
    )
    return folder, messages, plan_md
