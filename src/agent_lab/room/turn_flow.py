"""Top-level run_room and continue_room_round entry points."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agent_lab.agents.registry import AgentId, available_agents
from agent_lab.agent.roster import resolve_active_agents
from agent_lab.attachments import describe_attachments
from agent_lab.run.control import RoomRunCancelled, is_cancelled
from agent_lab.room.messages import (
    ChatMessage,
    DEFAULT_AGENT_PARALLEL_ROUNDS,
    OnAgentEvent,
    _agent_turn_summary,
    _emit_turn_terminal_status,
    _human_turn_count,
    _review_advocate,
    _turn_status_from_replies,
)

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
    _read_run_meta,
    _session_context,
    _sse_inbox_pending,
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
    _verified_loop_complete_payload,
    _verified_loop_continue_message,
    maybe_auto_scribe_after_consensus,
    maybe_auto_scribe_after_verified_loop,
)


def _emit_divergence_options(
    run_meta: dict[str, Any] | None,
    replies: list[ChatMessage],
    on_event: OnAgentEvent | None,
    cancelled: bool,
) -> None:
    """Emit the divergence options list as the terminal artifact of a 발산 run.

    No-op unless run_meta selects a divergence turn profile. Divergence stops
    here: this emits the options for human selection and never triggers execute.
    """
    from agent_lab.divergence import format_divergence_options, is_divergence_profile

    profile = str((run_meta or {}).get("turn_profile") or "")
    if cancelled or not on_event or not replies or not is_divergence_profile(profile):
        return
    options = format_divergence_options(replies)
    if options:
        on_event("divergence_options", {"options": options, "count": len(options)})


def _session_hard_cap_enabled() -> bool:
    import os

    return (os.getenv("AGENT_LAB_SESSION_HARD_CAP") or "").strip().lower() in ("1", "true", "yes", "on")


def _emit_budget_status(run_meta: dict[str, Any] | None, on_event: OnAgentEvent | None) -> None:
    """Surface cumulative session cost each turn and trip adaptive efficiency on over.

    Always emits a budget_status event (cost is visible even with no budget set).
    On the first over-transition, enables adaptive efficiency for subsequent turns
    and announces it once; mission/loop circuit-breakers are untouched.
    """
    if not on_event or not isinstance(run_meta, dict):
        return
    from agent_lab.cost_ledger import session_budget_action

    action = session_budget_action(run_meta)
    run_meta["budget_status"] = {
        "warn": action["warn"],
        "over": action["over"],
        "budget_set": action["budget_set"],
        "cumulative": action["cumulative"],
    }
    on_event("budget_status", action)
    if action.get("over") and not run_meta.get("adaptive_efficiency"):
        run_meta["adaptive_efficiency"] = True
        on_event(
            "efficiency_auto_enabled",
            {
                "reason": "session_budget_over",
                "cumulative": action.get("cumulative"),
                "usd_limit": action.get("usd_limit"),
                "token_limit": action.get("token_limit"),
            },
        )
    if action.get("over") and _session_hard_cap_enabled() and not run_meta.get("budget_exhausted"):
        run_meta["budget_exhausted"] = True
        on_event("budget_exhausted", {"cumulative": action.get("cumulative")})


def _resolve_stage_routing(
    run_meta: dict[str, Any],
    *,
    turn_profile: str | None,
    consensus_mode: bool,
    folder: Path | None,
) -> bool:
    """Phase-aware single-vs-panel routing (no-op unless AGENT_LAB_STAGE_ROUTING is on).

    Returns the resolved consensus_mode and records the observational RoutingDecisionLog.
    OFF-parity: with the flag off the input consensus_mode is returned unchanged and nothing
    is written.
    """
    from agent_lab.turn_modes import stage_routing_enabled

    if not stage_routing_enabled():
        return consensus_mode
    from agent_lab.mode_router import record_routing_decision, resolve_active_phase
    from agent_lab.turn_modes import stage_route_consensus

    resolved, decision = stage_route_consensus(
        phase=resolve_active_phase(run_meta),
        turn_profile=turn_profile,
        consensus_mode=consensus_mode,
        stage_routing=True,
    )
    record_routing_decision(folder, decision)
    return resolved


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
            pass
    messages = load_session_messages(folder)
    body = user_message.strip()
    att = describe_attachments(folder)
    if att:
        body = f"{body}\n\n---\n\n{att}"
    human_turn_index = _human_turn_count(messages)
    messages.append(ChatMessage(role="user", agent=None, content=body))
    human_turn_num = _human_turn_count(messages)
    from agent_lab.human_inbox import supersede_pending_inbox
    from agent_lab.mission.board import begin_human_turn

    begin_human_turn(folder, human_turn=human_turn_num)
    supersede_pending_inbox(folder, human_turn_id=human_turn_num)
    plan_md, run_meta = _session_context(folder)
    efficiency_mode = efficiency_mode or bool((run_meta or {}).get("adaptive_efficiency"))
    from agent_lab.inbox.harvest import clear_inbox_fork_grace

    clear_inbox_fork_grace(run_meta)
    _bind_session_to_run_meta(run_meta, folder)
    active_agents = resolve_active_agents(agents, available_agents, session_folder=folder)
    from agent_lab.agent.availability import filter_agents_for_turn

    active_agents = filter_agents_for_turn(
        active_agents,
        run_meta=run_meta,
        available_fn=available_agents,
    )
    mode = "plan" if synthesize else "discuss"
    review_advocate = _review_advocate(active_agents, human_turn_index) if review_mode and active_agents else None
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
        should_enable_plan_workflow,
    )

    if should_enable_plan_workflow(synthesize=synthesize):
        init_plan_workflow_on_plan_send(folder)
        plan_md, run_meta = _session_context(folder)
        _bind_session_to_run_meta(run_meta, folder)
    from agent_lab.trace_recorder import install_tracer

    on_event = install_tracer(folder, run_meta, on_event, human_turn=human_turn_num)
    if turn_profile:
        tp = (turn_profile or "analyze").strip().lower()
        run_meta["turn_profile"] = "analyze" if tp == "discuss" else tp
        if run_meta["turn_profile"] == "specialist":
            from agent_lab.room.agent_capabilities import ensure_specialist_capabilities

            if not run_meta.get("agent_capabilities_custom"):
                ensure_specialist_capabilities(run_meta)
            parallel_rounds = max(parallel_rounds, 2)
        from agent_lab.plan.workflow import apply_legacy_verified_turn_profile

        apply_legacy_verified_turn_profile(folder, run_meta, synthesize=synthesize)
    if research_mode or run_meta.get("turn_profile") == "specialist":
        run_meta["research_mode"] = True
    from agent_lab.session.clarifier import (
        build_clarifier_interview,
        interview_prompts,
        persist_clarifier_interview,
        sync_clarifier_answers_from_inbox,
    )

    sync_clarifier_answers_from_inbox(folder)
    skip_server_clarifier = plan_workflow_skips_server_clarifier(run_meta)
    clarifier_interview = None
    clarifier_questions: list[str] | None = None
    if not skip_server_clarifier:
        clarifier_interview = build_clarifier_interview(
            body,
            is_new_session=False,
            human_message_count=human_turn_num,
            plan_mode=synthesize,
        )
        if clarifier_interview:
            persisted = persist_clarifier_interview(folder, clarifier_interview)
            clarifier_interview = persisted.get("interview") or clarifier_interview
        clarifier_questions = interview_prompts(clarifier_interview)
        if clarifier_questions and on_event:
            on_event(
                "clarifier_prompt",
                {"questions": clarifier_questions, "interview": clarifier_interview},
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
    replies: list[ChatMessage] = []
    cancelled = False
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
                consensus_meta.setdefault("category", run_meta["_turn_category"])
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
    messages.extend(replies)
    _emit_divergence_options(run_meta, replies, on_event, cancelled)
    _emit_budget_status(run_meta, on_event)
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
    from agent_lab.plan.workflow import is_plan_workflow_active, plan_workflow_complete_payload, plan_workflow_phase

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
    )
    communicate_meta = _communicate_meta_for_turn(
        replies,
        context_log,
        parallel_rounds=parallel_rounds,
        review_mode=review_mode,
        consensus_mode=consensus_mode,
        turn_profile=turn_profile or str(run_meta.get("turn_profile") or ""),
        efficiency_mode=efficiency_mode,
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
    auto_plan = maybe_auto_scribe_after_verified_loop(
        folder,
        verified_result=verified_result,
        cancelled=cancelled,
        on_event=on_event,
        permissions=permissions,
    )
    if auto_plan is not None:
        plan_md = auto_plan
    elif not normalize_verified_profile(active_profile):
        auto_plan = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta=consensus_meta,
            synthesize=synthesize,
            cancelled=cancelled,
            on_event=on_event,
            permissions=permissions,
        )
        if auto_plan is not None:
            plan_md = auto_plan
    if on_event:
        on_event(
            "complete",
            {
                "session_id": folder.name,
                "path": str(folder),
                "cancelled": cancelled,
                "status": turn_status,
                "failed_agents": turn_summary["failed_agents"],
                "succeeded_agents": turn_summary["succeeded_agents"],
                "send_receipt": send_receipt_val,
                "inbox_pending": _sse_inbox_pending(folder),
                "turn_index": max(
                    0,
                    len((_read_run_meta(folder).get("turns") or [])) - 1,
                ),
                **_verified_loop_complete_payload(verified_result),
                **plan_workflow_complete_payload(folder),
            },
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
    body = topic.strip()
    if session_folder and session_folder.is_dir():
        att = describe_attachments(session_folder)
        if att:
            body = f"{body}\n\n---\n\n{att}"
    messages: list[ChatMessage] = [ChatMessage(role="user", agent=None, content=body)]
    folder: Path | None = None
    if session_folder and session_folder.is_dir():
        folder = session_folder
        if (folder / "topic.txt").is_file():
            topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
        messages = load_session_messages(folder) + messages

    plan_md, run_meta = _session_context(folder)
    _bind_session_to_run_meta(run_meta, folder)
    active_agents = resolve_active_agents(agents, available_agents, session_folder=folder)
    from agent_lab.agent.availability import filter_agents_for_turn

    active_agents = filter_agents_for_turn(
        active_agents,
        run_meta=run_meta,
        available_fn=available_agents,
    )
    human_turn_index = _human_turn_count(messages) - 1
    mode = "plan" if synthesize else "discuss"
    review_advocate = (
        _review_advocate(active_agents, max(0, human_turn_index)) if review_mode and active_agents else None
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
    from agent_lab.trace_recorder import install_tracer

    on_event = install_tracer(folder, run_meta, on_event, human_turn=human_turn_num)
    from agent_lab.room.team_orchestration import resolve_turn_lead

    resolve_turn_lead(
        run_meta,
        human_turn_num,
        [str(a) for a in active_agents],
        user_message=topic,
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
        should_enable_plan_workflow,
    )

    if folder is not None and should_enable_plan_workflow(synthesize=synthesize):
        init_plan_workflow_on_plan_send(folder)
        plan_md, run_meta = _session_context(folder)
        _bind_session_to_run_meta(run_meta, folder)
    if turn_profile:
        tp = (turn_profile or "analyze").strip().lower()
        run_meta["turn_profile"] = "analyze" if tp == "discuss" else tp
        if run_meta["turn_profile"] == "specialist":
            from agent_lab.room.agent_capabilities import ensure_specialist_capabilities

            if not run_meta.get("agent_capabilities_custom"):
                ensure_specialist_capabilities(run_meta)
            parallel_rounds = max(parallel_rounds, 2)
        from agent_lab.plan.workflow import apply_legacy_verified_turn_profile

        apply_legacy_verified_turn_profile(folder, run_meta, synthesize=synthesize)
    if research_mode or run_meta.get("turn_profile") == "specialist":
        run_meta["research_mode"] = True
    from agent_lab.session.clarifier import (
        build_clarifier_interview,
        interview_prompts,
        persist_clarifier_interview,
        sync_clarifier_answers_from_inbox,
    )

    is_new = folder is None or not (folder / "chat.jsonl").is_file()
    if folder is not None:
        sync_clarifier_answers_from_inbox(folder)
    skip_server_clarifier = plan_workflow_skips_server_clarifier(run_meta)
    clarifier_interview = None
    clarifier_questions: list[str] | None = None
    if not skip_server_clarifier:
        clarifier_interview = build_clarifier_interview(
            body,
            is_new_session=is_new,
            human_message_count=human_turn_num,
            plan_mode=synthesize,
        )
        if clarifier_interview and folder is not None:
            persisted = persist_clarifier_interview(folder, clarifier_interview)
            clarifier_interview = persisted.get("interview") or clarifier_interview
        clarifier_questions = interview_prompts(clarifier_interview)
        if clarifier_questions and on_event:
            on_event(
                "clarifier_prompt",
                {"questions": clarifier_questions, "interview": clarifier_interview},
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
    replies: list[ChatMessage] = []
    cancelled = False
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
                human_turn_index=max(0, human_turn_index),
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
            parallel_rounds = consensus_meta.get("rounds", 1) if consensus_meta else 1
            if consensus_meta is not None and run_meta.get("_turn_category"):
                consensus_meta.setdefault("category", run_meta["_turn_category"])
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
                human_turn_index=max(0, human_turn_index),
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
    messages.extend(replies)
    _emit_divergence_options(run_meta, replies, on_event, cancelled)
    _emit_budget_status(run_meta, on_event)

    plan_before = _read_plan_before(folder)
    plan_md = plan_before
    if folder is not None:
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
        if synthesize and scribe_applied and not plan_md:
            plan_md = "## Plan synthesis failed\n\nunknown error"
    else:
        scribe_applied = _should_scribe_plan_after_turn(synthesize=synthesize, cancelled=cancelled)
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
            if synthesize and not plan_md:
                plan_md = "## Plan synthesis failed\n\nunknown error"
    plan_trigger = _plan_trigger_for_turn(synthesize=synthesize, scribe_applied=scribe_applied)

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
    from agent_lab.plan.workflow import is_plan_workflow_active, plan_workflow_complete_payload, plan_workflow_phase

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
    )
    communicate_meta = _communicate_meta_for_turn(
        replies,
        context_log,
        parallel_rounds=parallel_rounds,
        review_mode=review_mode,
        consensus_mode=consensus_mode,
        turn_profile=turn_profile or str(run_meta.get("turn_profile") or ""),
        efficiency_mode=efficiency_mode,
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
        if should_enable_plan_workflow(synthesize=synthesize):
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
    auto_plan = maybe_auto_scribe_after_verified_loop(
        folder,
        verified_result=verified_result,
        cancelled=cancelled,
        on_event=on_event,
        permissions=permissions,
    )
    if auto_plan is not None:
        plan_md = auto_plan
    elif not normalize_verified_profile(active_profile):
        auto_plan = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta=consensus_meta,
            synthesize=synthesize,
            cancelled=cancelled,
            on_event=on_event,
            permissions=permissions,
        )
        if auto_plan is not None:
            plan_md = auto_plan
    if on_event:
        on_event(
            "complete",
            {
                "session_id": folder.name,
                "path": str(folder),
                "cancelled": cancelled,
                "status": turn_status,
                "failed_agents": turn_summary["failed_agents"],
                "succeeded_agents": turn_summary["succeeded_agents"],
                "send_receipt": send_receipt_val,
                "inbox_pending": _sse_inbox_pending(folder),
                "turn_index": max(
                    0,
                    len((_read_run_meta(folder).get("turns") or [])) - 1,
                ),
                **_verified_loop_complete_payload(verified_result),
                **plan_workflow_complete_payload(folder),
            },
        )
    return folder, messages, plan_md
