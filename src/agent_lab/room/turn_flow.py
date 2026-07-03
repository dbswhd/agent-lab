"""Top-level run_room and continue_room_round entry points."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

from agent_lab.agents.registry import AgentId, available_agents
from agent_lab.agent.roster import resolve_active_agents
from agent_lab.attachments import describe_attachments
from agent_lab.run.control import is_cancelled
from agent_lab.room.messages import (
    ChatMessage,
    DEFAULT_AGENT_PARALLEL_ROUNDS,
    OnAgentEvent,
    _agent_turn_summary,
    _emit_turn_terminal_status,
    _human_turn_count,
    _turn_status_from_replies,
)
from agent_lab.role_plan import resolve_review_advocate

from agent_lab.room.agent_invoke import (
    _bind_session_to_run_meta,
    _finalize_durable_turn,
    _set_active_turn_flags,
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
    _prepare_team_coordination_before_round,
    _session_context,
    _write_session_files,
    load_session_messages,
    save_room_session,
)

from agent_lab.room.turn_meta import (
    _communicate_meta_for_turn,
    _delegate_run_meta_patch,
    _final_turn_state_dict,
    _goal_auto_continue_message,
    _maybe_verified_loop_after_turn,
    _peer_metrics_for_messages,
    _try_delegate_turn,
    _turn_snapshot,
    _verified_loop_continue_message,
)


from agent_lab.room.turn_flow_finalize import apply_post_turn_auto_scribe, emit_turn_complete_event
from agent_lab.room.turn_flow_rounds import run_turn_agent_rounds
from agent_lab.room.turn_flow_setup import apply_turn_profile_flags, prepare_clarifier_for_turn
from agent_lab.room.turn_flow_support import (
    _checkpoint_chat,
    _emit_budget_status,
    _emit_divergence_options,
    _resolve_stage_routing,
    _session_hard_cap_enabled,
    after_agent_replies_checkpoint,
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
    from agent_lab.room.turn_policy import TurnSignals, apply_turn_effects, turn_policy_enabled

    if turn_policy_enabled():
        result = apply_turn_effects(
            signals=TurnSignals.from_run_meta(
                run_meta,
                consensus_meta=consensus_meta,
                legacy_synthesize_hint=synthesize,
                cancelled=cancelled,
            ),
            folder=folder,
            topic=topic,
            messages=messages,
            run_meta=run_meta,
            plan_before=plan_before,
            mode=mode,
            legacy_synthesize=synthesize,
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
    from agent_lab.room.turn_flow_support import (
        apply_turn_agent_mentions,
        direct_turn_for_mention_targets,
    )

    user_text, active_agents, mention_targets, mention_error = apply_turn_agent_mentions(
        user_text,
        active_agents,
        run_meta,
        roster_pool=requested_agents,
    )
    body = user_text
    if att:
        body = f"{body}\n\n---\n\n{att}" if body else att
    messages.append(ChatMessage(role="user", agent=None, content=body))
    _checkpoint_chat(folder, messages, topic=topic)
    from agent_lab.trace_recorder import install_tracer

    on_event = install_tracer(folder, run_meta, on_event, human_turn=human_turn_num)
    if mention_error:
        mode = "plan" if synthesize else "discuss"
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
    if direct_turn_for_mention_targets(mention_targets):
        consensus_mode = False
    from agent_lab.human_inbox import supersede_pending_inbox
    from agent_lab.mission.board import begin_human_turn

    begin_human_turn(folder, human_turn=human_turn_num)
    supersede_pending_inbox(folder, human_turn_id=human_turn_num)
    run_meta["agents"] = [str(a) for a in active_agents]
    mode = "plan" if synthesize else "discuss"
    review_advocate = (
        resolve_review_advocate(
            active_agents,
            human_turn_index,
            run_meta=run_meta,
            review_mode=bool(review_mode),
        )
        if review_mode and active_agents
        else None
    )
    from agent_lab.room.team_orchestration import resolve_turn_lead

    resolve_turn_lead(
        run_meta,
        human_turn_num,
        [str(a) for a in active_agents],
        user_message=body,
    )

    consensus_mode = _resolve_stage_routing(
        run_meta, turn_profile=turn_profile, consensus_mode=consensus_mode, folder=folder
    )

    _set_active_turn_flags(
        run_meta,
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
    )
    from agent_lab.plan.workflow import (
        init_plan_workflow_on_plan_send,
        plan_workflow_skips_server_clarifier,
        plan_workflow_wants_inbox_mcp,
        should_enable_plan_workflow,
    )
    from agent_lab.room.turn_policy import prepare_turn_policy_before_agent_round, turn_policy_enabled

    if turn_policy_enabled():
        run_meta, _tp_pre = prepare_turn_policy_before_agent_round(
            folder,
            run_meta,
            synthesize=synthesize,
            human_turn=human_turn_num,
        )
        plan_md, run_meta = _session_context(folder)
        _bind_session_to_run_meta(run_meta, folder)
    elif should_enable_plan_workflow(synthesize=synthesize):
        init_plan_workflow_on_plan_send(folder)
        plan_md, run_meta = _session_context(folder)
        _bind_session_to_run_meta(run_meta, folder)
    from agent_lab.room.turn_flow_support import ensure_adaptive_efficiency_for_turn

    ensure_adaptive_efficiency_for_turn(run_meta, human_turn=human_turn_num)
    parallel_rounds = apply_turn_profile_flags(
        run_meta,
        turn_profile,
        synthesize=synthesize,
        folder=folder,
        parallel_rounds=parallel_rounds,
        research_mode=research_mode,
    )
    from agent_lab.session.clarifier import sync_clarifier_answers_from_inbox

    sync_clarifier_answers_from_inbox(folder)
    if folder is not None and plan_workflow_wants_inbox_mcp(run_meta):
        from agent_lab.plan.workflow import ensure_plan_clarify_interview, ensure_plan_clarify_inbox_question

        ensure_plan_clarify_interview(folder)
        ensure_plan_clarify_inbox_question(folder)
    skip_server_clarifier = plan_workflow_skips_server_clarifier(run_meta)
    clarifier_questions = prepare_clarifier_for_turn(
        folder,
        body,
        is_new_session=False,
        human_turn_num=human_turn_num,
        synthesize=synthesize,
        skip_server_clarifier=skip_server_clarifier,
        on_event=on_event,
    )
    t0 = time.perf_counter()
    context_log: list[dict[str, Any]] = []
    _prepare_team_coordination_before_round(
        folder,
        run_meta,
        active_agents,
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
    )
    consensus_meta: dict[str, Any] | None = None
    plan_before = (folder / "plan.md").read_text(encoding="utf-8") if (folder / "plan.md").is_file() else ""
    delegate_replies = _try_delegate_turn(
        body=body,
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        folder=folder,
        permissions=permissions,
        on_event=on_event,
        clarifier_questions=clarifier_questions,
        human_turn_num=human_turn_num,
    )
    replies, consensus_meta, parallel_rounds, cancelled = run_turn_agent_rounds(
        topic=topic,
        messages=messages,
        agents=active_agents,
        clarifier_questions=clarifier_questions,
        delegate_replies=delegate_replies,
        consensus_mode=consensus_mode,
        parallel_rounds=parallel_rounds,
        on_event=on_event,
        permissions=permissions,
        human_turn_index=human_turn_index,
        plan_md=plan_md,
        run_meta=run_meta,
        context_log=context_log,
        efficiency_mode=efficiency_mode,
        review_mode=review_mode,
    )
    messages.extend(replies)
    after_agent_replies_checkpoint(
        folder,
        messages,
        topic=topic,
        run_meta=run_meta,
        replies=replies,
        on_event=on_event,
        cancelled=cancelled,
    )
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
    _checkpoint_chat(folder, messages, topic=topic)
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
    existing_meta: dict[str, Any] = {}
    meta_path = folder / "meta.json"
    if meta_path.is_file():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    from agent_lab.room.tasks import team_lead
    from agent_lab.room.team_orchestration import resolve_send_receipt, turn_leads_map
    from agent_lab.plan.workflow import is_plan_workflow_active, plan_workflow_phase

    plan_updated = bool(not cancelled and scribe_applied and plan_md and plan_md != plan_before)
    pw_phase = plan_workflow_phase(run_meta) if is_plan_workflow_active(run_meta) else None
    peer = _peer_metrics_for_messages(messages)
    send_receipt_val = resolve_send_receipt(
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
        consensus=consensus_meta,
        plan_updated=plan_updated,
        status=turn_status,
        plan_workflow_phase=pw_phase,
        turn_policy=run_meta.get("turn_policy") if isinstance(run_meta.get("turn_policy"), dict) else None,
        turn_kind=str(run_meta.get("turn_kind") or "") or None,
    )
    communicate_meta = _communicate_meta_for_turn(
        replies,
        context_log,
        parallel_rounds=parallel_rounds,
        review_mode=review_mode,
        consensus_mode=consensus_mode,
        turn_profile=turn_profile or str(run_meta.get("turn_profile") or ""),
        efficiency_mode=efficiency_mode,
        run_meta=run_meta,
    )
    from agent_lab.goal_loop import (
        goal_auto_continue_enabled,
        maybe_check_session_goal_after_turn,
    )
    from agent_lab.plan.workflow import plan_workflow_skips_goal_check
    from agent_lab.verified_loop import normalize_verified_profile

    active_profile = turn_profile or run_meta.get("turn_profile")
    verified_result = _maybe_verified_loop_after_turn(
        folder,
        messages,
        active_profile,
        cancelled=cancelled,
    )
    # Hard stop: a cancelled agent can be swallowed into a message without raising,
    # so the local `cancelled` flag may be False even though the run was cancelled.
    # Consult the global cancel flag so verified-loop / goal continuations never run
    # after ⌘. (issue E).
    verified_continue = None if (cancelled or is_cancelled()) else _verified_loop_continue_message(verified_result)
    _write_session_files(
        folder,
        topic,
        messages,
        plan_md,
        agents_used=active_agents,
        merge_meta={**existing_meta, "topic": topic},
        turn_meta=_turn_snapshot(
            mode=mode,
            synthesize=synthesize,
            agents_used=active_agents,
            parallel_rounds=parallel_rounds,
            permissions=permissions,
            latency_ms=latency_ms,
            status=turn_status,
            review_mode=review_mode,
            review_advocate=review_advocate,
            context_log=context_log,
            consensus_mode=consensus_mode,
            consensus=consensus_meta,
            efficiency_mode=efficiency_mode,
            turn_state=_final_turn_state_dict(
                messages,
                run_meta=run_meta,
                active_agents=active_agents,
                consensus_meta=consensus_meta,
                plan_md=plan_md,
            ),
            turn_profile=turn_profile,
            turn_lead=team_lead(run_meta),
            turn_leads=turn_leads_map(run_meta),
            send_receipt=send_receipt_val,
            peer_message_count=int(peer.get("peer_message_count") or 0),
            agents_with_r2_reply=list(peer.get("agents_with_r2_reply") or []),
            failed_agents=turn_summary["failed_agents"],
            succeeded_agents=turn_summary["succeeded_agents"],
            last_delegate=run_meta.get("last_delegate"),
            plan_trigger=plan_trigger,
            communicate_meta=communicate_meta,
            category=run_meta.get("_turn_category"),
            roles=run_meta.get("_turn_roles") or None,
            turn_policy=run_meta.get("turn_policy") if isinstance(run_meta.get("turn_policy"), dict) else None,
            turn_kind=str(run_meta.get("turn_kind") or "") or None,
        ),
        run_meta_patch=_delegate_run_meta_patch(run_meta),
        clarifier_questions=clarifier_questions,
    )
    # S1 Phase A: run AFTER _write_session_files so run.json has the current turn's
    # snapshot (category, roles, advisor_rationale) before record_turn_outcome reads it.
    _finalize_durable_turn(folder, human_turn_num, turn_status)
    if verified_continue and _verified_loop_depth < 3:
        return continue_room_round(
            folder,
            verified_continue,
            agents=active_agents,
            synthesize=False,
            parallel_rounds=1,
            on_event=on_event,
            permissions=permissions,
            review_mode=False,
            consensus_mode=False,
            efficiency_mode=efficiency_mode,
            turn_profile=active_profile or "verified",
            research_mode=research_mode,
            _goal_auto_continue_depth=_goal_auto_continue_depth,
            _verified_loop_depth=_verified_loop_depth + 1,
        )

    goal_result = None
    if not normalize_verified_profile(active_profile) and not plan_workflow_skips_goal_check(run_meta):
        goal_result = maybe_check_session_goal_after_turn(folder, messages)
    goal_continue = _goal_auto_continue_message(goal_result)
    if goal_auto_continue_enabled() and goal_continue and not is_cancelled() and _goal_auto_continue_depth < 1:
        return continue_room_round(
            folder,
            goal_continue,
            agents=active_agents,
            synthesize=False,
            parallel_rounds=1,
            on_event=on_event,
            permissions=permissions,
            review_mode=False,
            consensus_mode=False,
            efficiency_mode=efficiency_mode,
            turn_profile="analyze",
            research_mode=research_mode,
            _goal_auto_continue_depth=1,
            _verified_loop_depth=_verified_loop_depth,
        )
    plan_md = apply_post_turn_auto_scribe(
        folder,
        verified_result=verified_result,
        consensus_meta=consensus_meta,
        active_profile=active_profile,
        synthesize=synthesize,
        cancelled=cancelled,
        on_event=on_event,
        permissions=permissions,
        plan_md=plan_md,
    )
    emit_turn_complete_event(
        folder,
        on_event=on_event,
        cancelled=cancelled,
        turn_status=turn_status,
        turn_summary=turn_summary,
        send_receipt_val=send_receipt_val,
        verified_result=verified_result,
    )
    return messages, plan_md


def run_room(
    topic: str,
    *,
    agents: list[AgentId] | None = None,
    synthesize: bool = True,
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
    from agent_lab.room.turn_flow_support import (
        apply_turn_agent_mentions,
        direct_turn_for_mention_targets,
    )

    user_text, active_agents, mention_targets, mention_error = apply_turn_agent_mentions(
        user_text,
        active_agents,
        run_meta,
        roster_pool=requested_agents,
    )
    body = user_text
    if att:
        body = f"{body}\n\n---\n\n{att}" if body else att
    messages: list[ChatMessage] = [ChatMessage(role="user", agent=None, content=body)]
    if folder is not None:
        messages = load_session_messages(folder) + messages
    run_meta["agents"] = [str(a) for a in active_agents]
    human_turn_index = _human_turn_count(messages) - 1
    mode = "plan" if synthesize else "discuss"
    review_advocate = (
        resolve_review_advocate(
            active_agents,
            max(0, human_turn_index),
            run_meta=run_meta,
            review_mode=bool(review_mode),
        )
        if review_mode and active_agents
        else None
    )
    efficiency_mode = efficiency_mode or bool((run_meta or {}).get("adaptive_efficiency"))
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
    if direct_turn_for_mention_targets(mention_targets):
        consensus_mode = False
    from agent_lab.room.turn_flow_support import ensure_adaptive_efficiency_for_turn

    ensure_adaptive_efficiency_for_turn(run_meta, human_turn=human_turn_num)
    from agent_lab.room.team_orchestration import resolve_turn_lead

    resolve_turn_lead(
        run_meta,
        human_turn_num,
        [str(a) for a in active_agents],
        user_message=body,
    )

    consensus_mode = _resolve_stage_routing(
        run_meta, turn_profile=turn_profile, consensus_mode=consensus_mode, folder=folder
    )

    _set_active_turn_flags(
        run_meta,
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
    )
    from agent_lab.plan.workflow import (
        init_plan_workflow_on_plan_send,
        plan_workflow_skips_server_clarifier,
        plan_workflow_wants_inbox_mcp,
        should_enable_plan_workflow,
    )
    from agent_lab.room.turn_policy import prepare_turn_policy_before_agent_round, turn_policy_enabled

    if folder is not None and turn_policy_enabled():
        run_meta, _tp_pre = prepare_turn_policy_before_agent_round(
            folder,
            run_meta,
            synthesize=synthesize,
            human_turn=human_turn_num,
        )
        plan_md, run_meta = _session_context(folder)
        _bind_session_to_run_meta(run_meta, folder)
    elif folder is not None and should_enable_plan_workflow(synthesize=synthesize):
        init_plan_workflow_on_plan_send(folder)
        plan_md, run_meta = _session_context(folder)
        _bind_session_to_run_meta(run_meta, folder)
    parallel_rounds = apply_turn_profile_flags(
        run_meta,
        turn_profile,
        synthesize=synthesize,
        folder=folder,
        parallel_rounds=parallel_rounds,
        research_mode=research_mode,
    )
    from agent_lab.session.clarifier import sync_clarifier_answers_from_inbox

    is_new = folder is None or not (folder / "chat.jsonl").is_file()
    if folder is not None:
        sync_clarifier_answers_from_inbox(folder)
        if plan_workflow_wants_inbox_mcp(run_meta):
            from agent_lab.plan.workflow import ensure_plan_clarify_interview, ensure_plan_clarify_inbox_question

            ensure_plan_clarify_interview(folder)
            ensure_plan_clarify_inbox_question(folder)
    skip_server_clarifier = plan_workflow_skips_server_clarifier(run_meta)
    clarifier_questions = prepare_clarifier_for_turn(
        folder,
        body,
        is_new_session=is_new,
        human_turn_num=human_turn_num,
        synthesize=synthesize,
        skip_server_clarifier=skip_server_clarifier,
        on_event=on_event,
    )
    t0 = time.perf_counter()
    context_log: list[dict[str, Any]] = []
    _prepare_team_coordination_before_round(
        folder,
        run_meta,
        active_agents,
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
    )
    consensus_meta: dict[str, Any] | None = None
    delegate_replies = None
    if folder is not None:
        delegate_replies = _try_delegate_turn(
            body=body,
            topic=topic,
            messages=messages,
            run_meta=run_meta,
            folder=folder,
            permissions=permissions,
            on_event=on_event,
            clarifier_questions=clarifier_questions,
            human_turn_num=human_turn_num,
        )
    replies, consensus_meta, parallel_rounds, cancelled = run_turn_agent_rounds(
        topic=topic,
        messages=messages,
        agents=active_agents,
        clarifier_questions=clarifier_questions,
        delegate_replies=delegate_replies,
        consensus_mode=consensus_mode,
        parallel_rounds=parallel_rounds,
        on_event=on_event,
        permissions=permissions,
        human_turn_index=max(0, human_turn_index),
        plan_md=plan_md,
        run_meta=run_meta,
        context_log=context_log,
        efficiency_mode=efficiency_mode,
        review_mode=review_mode,
    )
    messages.extend(replies)
    after_agent_replies_checkpoint(
        folder,
        messages,
        topic=topic,
        run_meta=run_meta,
        replies=replies,
        on_event=on_event,
        cancelled=cancelled,
    )

    plan_before = _read_plan_before(folder)
    plan_md = plan_before
    if folder is not None:
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
        _checkpoint_chat(folder, messages, topic=topic)
    else:
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
    from agent_lab.room.tasks import team_lead
    from agent_lab.room.team_orchestration import resolve_send_receipt, turn_leads_map
    from agent_lab.plan.workflow import is_plan_workflow_active, plan_workflow_phase

    peer = _peer_metrics_for_messages(messages)
    pw_phase = plan_workflow_phase(run_meta) if is_plan_workflow_active(run_meta) else None
    send_receipt_val = resolve_send_receipt(
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
        consensus=consensus_meta,
        plan_updated=bool(scribe_applied and not cancelled and plan_md and plan_md != plan_before),
        status=turn_status,
        plan_workflow_phase=pw_phase,
        turn_policy=run_meta.get("turn_policy") if isinstance(run_meta.get("turn_policy"), dict) else None,
        turn_kind=str(run_meta.get("turn_kind") or "") or None,
    )
    communicate_meta = _communicate_meta_for_turn(
        replies,
        context_log,
        parallel_rounds=parallel_rounds,
        review_mode=review_mode,
        consensus_mode=consensus_mode,
        turn_profile=turn_profile or str(run_meta.get("turn_profile") or ""),
        efficiency_mode=efficiency_mode,
        run_meta=run_meta,
    )
    turn_meta = _turn_snapshot(
        mode=mode,
        synthesize=synthesize,
        agents_used=active_agents,
        parallel_rounds=parallel_rounds,
        permissions=permissions,
        latency_ms=latency_ms,
        status=turn_status,
        review_mode=review_mode,
        review_advocate=review_advocate,
        context_log=context_log,
        consensus_mode=consensus_mode,
        consensus=consensus_meta,
        efficiency_mode=efficiency_mode,
        turn_state=_final_turn_state_dict(
            messages,
            run_meta=run_meta,
            active_agents=active_agents,
            consensus_meta=consensus_meta,
            plan_md=plan_md,
        ),
        turn_profile=turn_profile,
        turn_lead=team_lead(run_meta),
        turn_leads=turn_leads_map(run_meta),
        send_receipt=send_receipt_val,
        peer_message_count=int(peer.get("peer_message_count") or 0),
        agents_with_r2_reply=list(peer.get("agents_with_r2_reply") or []),
        failed_agents=turn_summary["failed_agents"],
        succeeded_agents=turn_summary["succeeded_agents"],
        last_delegate=run_meta.get("last_delegate"),
        plan_trigger=plan_trigger,
        communicate_meta=communicate_meta,
        category=run_meta.get("_turn_category"),
        roles=run_meta.get("_turn_roles") or None,
        turn_policy=run_meta.get("turn_policy") if isinstance(run_meta.get("turn_policy"), dict) else None,
        turn_kind=str(run_meta.get("turn_kind") or "") or None,
    )

    from agent_lab.goal_loop import (
        goal_auto_continue_enabled,
        maybe_check_session_goal_after_turn,
    )
    from agent_lab.plan.workflow import plan_workflow_skips_goal_check
    from agent_lab.verified_loop import normalize_verified_profile

    active_profile = turn_profile or run_meta.get("turn_profile")
    verified_result: dict[str, Any] | None = None
    if folder is not None:
        verified_result = _maybe_verified_loop_after_turn(
            folder,
            messages,
            active_profile,
            cancelled=cancelled,
        )
    # Hard stop: a cancelled agent can be swallowed into a message without raising,
    # so the local `cancelled` flag may be False even though the run was cancelled.
    # Consult the global cancel flag so verified-loop / goal continuations never run
    # after ⌘. (issue E).
    verified_continue = None if (cancelled or is_cancelled()) else _verified_loop_continue_message(verified_result)

    from agent_lab.plan.workflow import init_plan_workflow_on_plan_send, should_enable_plan_workflow
    from agent_lab.room.turn_policy import turn_policy_enabled

    if folder is None:
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
    else:
        existing_meta: dict[str, Any] = {}
        if (folder / "meta.json").is_file():
            try:
                existing_meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        _write_session_files(
            folder,
            topic,
            messages,
            plan_md,
            agents_used=active_agents,
            merge_meta=existing_meta,
            turn_meta=turn_meta,
            run_meta_patch=_delegate_run_meta_patch(run_meta),
            clarifier_questions=clarifier_questions,
        )
    _finalize_durable_turn(folder, 1, turn_status)
    if verified_continue:
        auto_messages, auto_plan_md = continue_room_round(
            folder,
            verified_continue,
            agents=active_agents,
            synthesize=False,
            parallel_rounds=1,
            on_event=on_event,
            permissions=permissions,
            review_mode=False,
            consensus_mode=False,
            efficiency_mode=efficiency_mode,
            turn_profile=active_profile or "verified",
            research_mode=research_mode,
            _verified_loop_depth=1,
        )
        return folder, auto_messages, auto_plan_md

    goal_result = None
    if not normalize_verified_profile(active_profile) and not plan_workflow_skips_goal_check(run_meta):
        goal_result = maybe_check_session_goal_after_turn(folder, messages)
    goal_continue = _goal_auto_continue_message(goal_result)
    if goal_auto_continue_enabled() and goal_continue and not is_cancelled():
        auto_messages, auto_plan_md = continue_room_round(
            folder,
            goal_continue,
            agents=active_agents,
            synthesize=False,
            parallel_rounds=1,
            on_event=on_event,
            permissions=permissions,
            review_mode=False,
            consensus_mode=False,
            efficiency_mode=efficiency_mode,
            turn_profile="analyze",
            research_mode=research_mode,
            _goal_auto_continue_depth=1,
        )
        return folder, auto_messages, auto_plan_md
    plan_md = apply_post_turn_auto_scribe(
        folder,
        verified_result=verified_result,
        consensus_meta=consensus_meta,
        active_profile=active_profile,
        synthesize=synthesize,
        cancelled=cancelled,
        on_event=on_event,
        permissions=permissions,
        plan_md=plan_md,
    )
    emit_turn_complete_event(
        folder,
        on_event=on_event,
        cancelled=cancelled,
        turn_status=turn_status,
        turn_summary=turn_summary,
        send_receipt_val=send_receipt_val,
        verified_result=verified_result,
    )
    return folder, messages, plan_md
