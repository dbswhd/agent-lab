"""F9 turn phase helpers — routing/consensus/harvest slices for turn_flow."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agent_lab.run.state import RunState, RunStateLike

from agent_lab.agents.registry import AgentId
from agent_lab.role_plan import resolve_review_advocate
from agent_lab.run.control import is_cancelled
from agent_lab.room.agent_invoke import _set_active_turn_flags
from agent_lab.room.messages import (
    ChatMessage,
    OnAgentEvent,
    _agent_turn_summary,
    _emit_turn_terminal_status,
    _turn_status_from_replies,
)
from agent_lab.room.session_persist import (
    _prepare_team_coordination_before_round,
    _session_context,
    _write_session_files,
)
from agent_lab.room.agent_invoke import _bind_session_to_run_meta
from agent_lab.room.turn_flow_finalize import apply_post_turn_auto_scribe, emit_turn_complete_event
from agent_lab.room.turn_flow_rounds import run_turn_agent_rounds
from agent_lab.room.turn_flow_setup import apply_turn_profile_flags, prepare_clarifier_for_turn
from agent_lab.room.turn_flow_support import (
    _resolve_stage_routing,
    after_agent_replies_checkpoint,
    direct_turn_for_mention_targets,
    ensure_adaptive_efficiency_for_turn,
)
from agent_lab.room.turn_meta import (
    _communicate_meta_for_turn,
    _final_turn_state_dict,
    _goal_auto_continue_message,
    _maybe_verified_loop_after_turn,
    _peer_metrics_for_messages,
    _turn_snapshot,
    _verified_loop_continue_message,
)


@dataclass(frozen=True, slots=True)
class TurnRoutingResult:
    run_meta: RunState
    plan_md: str
    mode: str
    review_advocate: str | None
    consensus_mode: bool
    parallel_rounds: int
    efficiency_mode: bool
    clarifier_questions: list[str] | None


def build_turn_body(user_text: str, attachment_desc: str) -> str:
    body = user_text.strip()
    att = attachment_desc.strip()
    if att:
        body = f"{body}\n\n---\n\n{att}" if body else att
    return body


def prepare_turn_routing_phase(
    *,
    folder: Path | None,
    run_meta: RunState,
    plan_md: str,
    body: str,
    active_agents: list[AgentId],
    mention_targets: list[str] | None,
    synthesize: bool,
    skill_intent: str | None = None,
    consensus_mode: bool,
    parallel_rounds: int,
    turn_profile: str | None,
    review_mode: bool,
    human_turn_index: int,
    human_turn_num: int,
    efficiency_mode: bool,
    research_mode: bool,
    on_event: OnAgentEvent | None,
    is_new_session: bool,
    begin_human_turn_hooks: bool = False,
) -> TurnRoutingResult:
    """Stage routing, turn flags, plan workflow, clarifier — §2.3 routing phase."""
    from agent_lab.plan.workflow import (
        ensure_plan_clarify_interview,
        ensure_plan_clarify_inbox_question,
        init_plan_workflow_on_plan_send,
        plan_workflow_skips_server_clarifier,
        plan_workflow_wants_inbox_mcp,
        should_enable_plan_workflow,
    )
    from agent_lab.room.turn_policy import (
        normalize_skill_intent,
        pop_pending_skill_intent,
        prepare_turn_policy_before_agent_round,
        stamp_active_skill_intent,
        turn_policy_enabled,
    )
    from agent_lab.room.team_orchestration import resolve_turn_lead
    from agent_lab.session.clarifier import sync_clarifier_answers_from_inbox

    if mention_targets and direct_turn_for_mention_targets(mention_targets):
        consensus_mode = False

    if begin_human_turn_hooks and folder is not None:
        from agent_lab.human_inbox import supersede_pending_inbox
        from agent_lab.mission.board import begin_human_turn

        begin_human_turn(folder, human_turn=human_turn_num)
        supersede_pending_inbox(folder, human_turn_id=human_turn_num)

    resolved_skill = normalize_skill_intent(skill_intent) or pop_pending_skill_intent(folder, run_meta)
    stamp_active_skill_intent(run_meta, resolved_skill)

    if turn_policy_enabled():
        mode = "discuss"
        active_synthesize = False
    else:
        mode = "plan" if synthesize else "discuss"
        active_synthesize = synthesize
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

    resolve_turn_lead(
        run_meta,
        human_turn_num,
        [str(a) for a in active_agents],
        user_message=body,
    )

    consensus_mode = _resolve_stage_routing(
        run_meta,
        turn_profile=turn_profile,
        consensus_mode=consensus_mode,
        folder=folder,
    )

    _set_active_turn_flags(
        run_meta,
        mode=mode,
        synthesize=active_synthesize,
        consensus_mode=consensus_mode,
    )

    if folder is not None:
        if turn_policy_enabled():
            run_meta, _tp_pre = prepare_turn_policy_before_agent_round(
                folder,
                run_meta,
                human_turn=human_turn_num,
                topic=body,
            )
            plan_md, run_meta = _session_context(folder)
            _bind_session_to_run_meta(run_meta, folder)
        elif should_enable_plan_workflow(synthesize=synthesize):
            init_plan_workflow_on_plan_send(folder)
            plan_md, run_meta = _session_context(folder)
            _bind_session_to_run_meta(run_meta, folder)

    ensure_adaptive_efficiency_for_turn(run_meta, human_turn=human_turn_num)
    efficiency_mode = efficiency_mode or bool(run_meta.get("adaptive_efficiency"))

    parallel_rounds = apply_turn_profile_flags(
        run_meta,
        turn_profile,
        synthesize=synthesize,
        folder=folder,
        parallel_rounds=parallel_rounds,
        research_mode=research_mode,
    )

    if folder is not None:
        sync_clarifier_answers_from_inbox(folder)
        if plan_workflow_wants_inbox_mcp(run_meta):
            from agent_lab.plan.workflow import plan_fsm_skill_first_enabled

            if not plan_fsm_skill_first_enabled():
                ensure_plan_clarify_interview(folder)
            ensure_plan_clarify_inbox_question(folder)

    skip_server_clarifier = plan_workflow_skips_server_clarifier(run_meta)
    clarifier_questions = prepare_clarifier_for_turn(
        folder,
        body,
        is_new_session=is_new_session,
        human_turn_num=human_turn_num,
        synthesize=synthesize,
        skip_server_clarifier=skip_server_clarifier,
        on_event=on_event,
    )

    return TurnRoutingResult(
        run_meta=run_meta,
        plan_md=plan_md,
        mode=mode,
        review_advocate=review_advocate,
        consensus_mode=consensus_mode,
        parallel_rounds=parallel_rounds,
        efficiency_mode=efficiency_mode,
        clarifier_questions=clarifier_questions,
    )


@dataclass(frozen=True, slots=True)
class ConsensusPhaseResult:
    replies: list[ChatMessage]
    consensus_meta: dict[str, Any] | None
    parallel_rounds: int
    cancelled: bool


def run_consensus_phase(
    *,
    topic: str,
    messages: list[ChatMessage],
    folder: Path | None,
    body: str,
    run_meta: RunStateLike,
    active_agents: list[AgentId],
    clarifier_questions: list[str] | None,
    consensus_mode: bool,
    parallel_rounds: int,
    on_event: OnAgentEvent | None,
    permissions: dict | None,
    human_turn_index: int,
    human_turn_num: int,
    plan_md: str,
    context_log: list[dict[str, Any]],
    efficiency_mode: bool,
    review_mode: bool,
    mode: str,
    synthesize: bool,
) -> ConsensusPhaseResult:
    """Agent rounds + checkpoint — §2.3 consensus phase."""
    from agent_lab.room.turn_meta import _try_delegate_turn

    _prepare_team_coordination_before_round(
        folder,
        run_meta,
        active_agents,
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
    )
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
    return ConsensusPhaseResult(
        replies=replies,
        consensus_meta=consensus_meta,
        parallel_rounds=parallel_rounds,
        cancelled=cancelled,
    )


def compose_turn_meta(
    *,
    mode: str,
    synthesize: bool,
    active_agents: list[AgentId],
    parallel_rounds: int,
    permissions: dict | None,
    latency_ms: int,
    turn_status: str,
    review_mode: bool,
    review_advocate: str | None,
    context_log: list[dict[str, Any]],
    consensus_mode: bool,
    consensus_meta: dict[str, Any] | None,
    efficiency_mode: bool,
    messages: list[ChatMessage],
    run_meta: RunStateLike,
    plan_md: str,
    turn_profile: str | None,
    send_receipt_val: str | None,
    turn_summary: dict[str, Any],
    plan_trigger: str | None,
    peer: dict[str, Any],
    replies: list[ChatMessage],
) -> dict[str, Any]:
    from agent_lab.room.tasks import team_lead
    from agent_lab.room.team_orchestration import turn_leads_map

    return _turn_snapshot(
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
        communicate_meta=_communicate_meta_for_turn(
            replies,
            context_log,
            parallel_rounds=parallel_rounds,
            review_mode=review_mode,
            consensus_mode=consensus_mode,
            turn_profile=turn_profile or str(run_meta.get("turn_profile") or ""),
            efficiency_mode=efficiency_mode,
            run_meta=run_meta,
        ),
        category=run_meta.get("_turn_category"),
        roles=run_meta.get("_turn_roles") or None,
        turn_policy=run_meta.get("turn_policy") if isinstance(run_meta.get("turn_policy"), dict) else None,
        turn_kind=str(run_meta.get("turn_kind") or "") or None,
    )


def harvest_existing_session_turn(
    folder: Path,
    *,
    topic: str,
    messages: list[ChatMessage],
    run_meta: RunStateLike,
    plan_before: str,
    mode: str,
    synthesize: bool,
    cancelled: bool,
    active_agents: list[AgentId],
    permissions: dict | None,
    on_event: OnAgentEvent | None,
    consensus_meta: dict[str, Any] | None,
    consensus_mode: bool,
    human_turn_num: int,
    turn_profile: str | None,
    review_mode: bool,
    review_advocate: str | None,
    parallel_rounds: int,
    context_log: list[dict[str, Any]],
    efficiency_mode: bool,
    research_mode: bool,
    clarifier_questions: list[str] | None,
    replies: list[ChatMessage],
    t0: float,
    post_agent_turn_plan: Callable[..., tuple[str, bool, dict[str, Any], str | None]],
    finalize_durable_turn: Callable[[Path, int, str], None],
    delegate_run_meta_patch: Callable[[dict[str, Any]], dict[str, Any] | None],
    continue_round: Callable[..., tuple[list[ChatMessage], str]],
    _goal_auto_continue_depth: int = 0,
    _verified_loop_depth: int = 0,
    merge_meta_extra: dict[str, Any] | None = None,
) -> tuple[list[ChatMessage], str]:
    """Post-consensus harvest for an on-disk session — plan, persist, auto-continue."""
    from agent_lab.goal_loop import goal_auto_continue_enabled, maybe_check_session_goal_after_turn
    from agent_lab.plan.workflow import (
        is_plan_workflow_active,
        plan_workflow_phase,
        plan_workflow_skips_goal_check,
    )
    from agent_lab.room.team_orchestration import resolve_send_receipt
    from agent_lab.verified_loop import normalize_verified_profile

    plan_md, scribe_applied, run_meta, plan_trigger = post_agent_turn_plan(
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
    from agent_lab.room.turn_flow_support import _checkpoint_chat

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
    if merge_meta_extra:
        existing_meta = {**existing_meta, **merge_meta_extra}
    plan_updated = bool(not cancelled and scribe_applied and plan_md and plan_md != plan_before)
    pw_phase = plan_workflow_phase(run_meta) if is_plan_workflow_active(run_meta) else None
    peer = _peer_metrics_for_messages(messages)
    active_profile = turn_profile or run_meta.get("turn_profile")
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
    verified_result = _maybe_verified_loop_after_turn(
        folder,
        messages,
        active_profile,
        cancelled=cancelled,
    )
    verified_continue = None if (cancelled or is_cancelled()) else _verified_loop_continue_message(verified_result)
    _write_session_files(
        folder,
        topic,
        messages,
        plan_md,
        agents_used=active_agents,
        merge_meta=existing_meta,
        turn_meta=turn_meta,
        run_meta_patch=delegate_run_meta_patch(run_meta),
        clarifier_questions=clarifier_questions,
    )
    finalize_durable_turn(folder, human_turn_num, turn_status)
    if verified_continue and _verified_loop_depth < 3:
        return continue_round(
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
        return continue_round(
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


@dataclass(frozen=True, slots=True)
class RunRoomStartResult:
    folder: Path | None
    topic: str
    messages: list[ChatMessage]
    plan_md: str
    run_meta: RunState
    active_agents: list[AgentId]
    mention_targets: list[str] | None
    body: str
    mode: str
    human_turn_index: int
    human_turn_num: int
    on_event: OnAgentEvent | None
    is_new: bool
    permissions: dict
    synthesize: bool
    sessions_base: Path | None
    abort: tuple[Path, list[ChatMessage], str] | None = None


def prepare_run_room_start(
    topic: str,
    *,
    agents: list[AgentId] | None,
    synthesize: bool,
    sessions_base: Path | None,
    session_folder: Path | None,
    permissions: dict | None,
    turn_profile: str | None,
    on_event: OnAgentEvent | None,
) -> RunRoomStartResult:
    """Session bootstrap + first user message before routing phase."""
    from agent_lab.agent.permissions import normalize_agent_permissions
    from agent_lab.agent.roster import resolve_active_agents
    from agent_lab.agents.registry import available_agents
    from agent_lab.attachments import describe_attachments
    from agent_lab.agent.availability import filter_agents_for_turn
    from agent_lab.room.plan_scribe import _bootstrap_session_folder_for_plan_workflow
    from agent_lab.room.session_persist import load_session_messages
    from agent_lab.room.turn_flow_abort import _abort_mention_roster_error
    from agent_lab.room.turn_flow_plan import _casual_turn_mode
    from agent_lab.room.turn_flow_support import _checkpoint_chat, apply_turn_agent_mentions
    from agent_lab.run.meta import stamp_run_meta
    from agent_lab.trace_recorder import install_tracer

    from agent_lab.room.agent_invoke import _bind_session_to_run_meta
    from agent_lab.room.messages import ChatMessage, _human_turn_count

    permissions_norm = normalize_agent_permissions(permissions)
    user_text = topic.strip()
    att = ""
    folder: Path | None = None
    if session_folder and session_folder.is_dir():
        folder = session_folder
        if (folder / "topic.txt").is_file():
            topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
        att = describe_attachments(folder)

    plan_md, run_meta = _session_context(folder)
    _bind_session_to_run_meta(run_meta, folder)
    requested_agents = resolve_active_agents(agents, available_agents, session_folder=folder)
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
            permissions=permissions_norm,
            turn_profile=turn_profile,
        )
        if folder is None:
            raise RuntimeError("mention roster error before session folder exists")
        return RunRoomStartResult(
            folder=folder,
            topic=topic,
            messages=messages,
            plan_md=plan_md,
            run_meta=run_meta,
            active_agents=active_agents,
            mention_targets=mention_targets,
            body=body,
            mode=mode,
            human_turn_index=max(0, human_turn_index),
            human_turn_num=human_turn_num,
            on_event=on_event,
            is_new=folder is None or not (folder / "chat.jsonl").is_file(),
            permissions=permissions_norm,
            synthesize=synthesize,
            sessions_base=sessions_base,
            abort=(folder, abort_messages, abort_plan_md),
        )
    is_new = folder is None or not (folder / "chat.jsonl").is_file()
    return RunRoomStartResult(
        folder=folder,
        topic=topic,
        messages=messages,
        plan_md=plan_md,
        run_meta=run_meta,
        active_agents=active_agents,
        mention_targets=mention_targets,
        body=body,
        mode=mode,
        human_turn_index=max(0, human_turn_index),
        human_turn_num=human_turn_num,
        on_event=on_event,
        is_new=is_new,
        permissions=permissions_norm,
        synthesize=synthesize,
        sessions_base=sessions_base,
    )


def harvest_new_session_turn(
    *,
    topic: str,
    messages: list[ChatMessage],
    run_meta: RunStateLike,
    active_agents: list[AgentId],
    mode: str,
    synthesize: bool,
    cancelled: bool,
    on_event: OnAgentEvent | None,
    consensus_meta: dict[str, Any] | None,
    consensus_mode: bool,
    parallel_rounds: int,
    permissions: dict | None,
    turn_profile: str | None,
    review_mode: bool,
    review_advocate: str | None,
    context_log: list[dict[str, Any]],
    efficiency_mode: bool,
    clarifier_questions: list[str] | None,
    replies: list[ChatMessage],
    t0: float,
    sessions_base: Path | None,
    finalize_durable_turn: Callable[[Path, int, str], None],
) -> tuple[Path, list[ChatMessage], str]:
    """Post-consensus harvest when the session folder is created at turn end."""
    from agent_lab.plan.workflow import init_plan_workflow_on_plan_send, should_enable_plan_workflow
    from agent_lab.room.plan_scribe import (
        _apply_scribe_after_turn,
        _plan_trigger_for_turn,
        _should_scribe_plan_after_turn,
    )
    from agent_lab.room.session_persist import save_room_session
    from agent_lab.room.team_orchestration import resolve_send_receipt
    from agent_lab.room.turn_policy import turn_policy_enabled

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
            session_folder=None,
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
    finalize_durable_turn(folder, 1, turn_status)
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
