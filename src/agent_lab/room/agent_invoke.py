"""Agent invocation and single-agent round helpers."""

from __future__ import annotations

from agent_lab.room._typing import agent_label
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.agents.registry import AgentId
from agent_lab.agent.envelope import (
    is_endorse_reply,
    is_pass_reply,
    parse_agent_response_v2,
)
from agent_lab.cli_retry import is_retryable, retry_attempts, retryable_failure
from agent_lab.run.control import RoomRunCancelled, is_cancelled
from agent_lab.room.messages import (
    ChatMessage,
    OnAgentEvent,
    _human_turn_number,
    build_agent_context_bundle,
)


_NON_PARTICIPATION_PATTERNS: dict[str, tuple[str, ...]] = {
    "usage_limit": ("usage limit", "rate limit", "429", "quota", "credit balance"),
    "timeout": (
        "no jsonl/stderr activity",
        "wall-clock timeout",
        "idle timeout",
        "stall",
    ),
}


def _non_participation_reason(error: Exception) -> str | None:
    """Classify a failure that should read as a calm 'sat out this turn' note —
    letting the rest of the team proceed — rather than a hard error.

    Alternate-model reassignment for the missing slot is tracked as Later in
    docs/AGENT-OS-MODE-SIMPLIFICATION-PLAN.md.
    """
    text = str(error).lower()
    for reason, needles in _NON_PARTICIPATION_PATTERNS.items():
        if any(needle in text for needle in needles):
            return reason
    return None


def _session_folder_from_run_meta(run_meta: RunStateLike | None) -> Path | None:
    if not run_meta:
        return None
    folder_raw = run_meta.get("_session_folder")
    if not folder_raw:
        return None
    folder = Path(str(folder_raw))
    return folder if folder.is_dir() else None


def _try_replay_completed_agent(
    aid: AgentId,
    *,
    human_turn_index: int,
    parallel_round: int,
    run_meta: RunStateLike | None,
    on_event: OnAgentEvent | None,
) -> ChatMessage | None:
    folder = _session_folder_from_run_meta(run_meta)
    if not folder:
        return None
    from agent_lab.run.meta import get_completed_step, read_run_meta

    human_turn = _human_turn_number(human_turn_index)
    run = run_meta or read_run_meta(folder)
    step = get_completed_step(
        run,
        human_turn=human_turn,
        parallel_round=parallel_round,
        agent=str(aid),
    )
    if not step:
        return None
    content = str(step.get("content") or "")
    envelope = step.get("envelope")
    if on_event:
        from agent_lab.room.sse_stream import emit_agent_tokens

        on_event(
            "agent_start",
            {"agent": aid, "round": parallel_round, "resumed": True},
        )
        emit_agent_tokens(
            on_event,
            agent=str(aid),
            round=parallel_round,
            text=content,
        )
        on_event(
            "agent_done",
            {
                "agent": aid,
                "round": parallel_round,
                "chars": len(content),
                "content": content,
                "pass": is_pass_reply(content, envelope if isinstance(envelope, dict) else None),
                "no_objection": is_endorse_reply(content, envelope if isinstance(envelope, dict) else None),
                "envelope": envelope,
                "envelope_valid": isinstance(envelope, dict),
                "resumed": True,
                "skipped_call": True,
                "completed_step": step.get("step"),
            },
        )
    from agent_lab.room.chat_channels import message_visibility

    return ChatMessage(
        role="agent",
        agent=aid,
        content=content,
        parallel_round=parallel_round,
        envelope=envelope if isinstance(envelope, dict) else None,
        visibility=message_visibility(role="agent", content=content),
    )


def _invoke_agent_for_round(
    aid: AgentId,
    *,
    topic: str,
    thread: list[ChatMessage],
    parallel_round: int,
    permissions: dict | None,
    review_mode: bool,
    review_advocate: AgentId | None,
    plan_md: str,
    run_meta: RunStateLike | None,
    on_event: OnAgentEvent | None,
    context_log: list[dict[str, Any]] | None = None,
    extra_follow_up: str = "",
    efficiency_mode: bool = False,
    slim_context: bool = False,
    human_turn_index: int = 0,
) -> ChatMessage:
    replay = _try_replay_completed_agent(
        aid,
        human_turn_index=human_turn_index,
        parallel_round=parallel_round,
        run_meta=run_meta,
        on_event=on_event,
    )
    if replay is not None:
        return replay
    return _call_one_agent(
        aid,
        topic=topic,
        thread=thread,
        parallel_round=parallel_round,
        permissions=permissions,
        review_mode=review_mode,
        review_advocate=review_advocate,
        plan_md=plan_md,
        run_meta=run_meta,
        on_event=on_event,
        context_log=context_log,
        extra_follow_up=extra_follow_up,
        efficiency_mode=efficiency_mode,
        slim_context=slim_context,
        human_turn_index=human_turn_index,
    )


def _finalize_durable_turn(folder: Path, human_turn_num: int, turn_status: str) -> None:
    if turn_status != "completed":
        return
    from agent_lab.run.meta import clear_completed_steps_for_human_turn

    clear_completed_steps_for_human_turn(folder, human_turn_num)

    # S1 Phase A: persist turn_metrics + append cross-session outcome ledger
    # (flag-gated, fail-open — never blocks turn completion).
    from agent_lab.outcome_harvester import record_turn_outcome

    record_turn_outcome(folder, human_turn_num)

    # N10a: harvest user-side corrections into the same outcome ledger
    # (flag-gated, fail-open — see docs/N10-USER-LOOP-WISDOM-DRAFT.md).
    from agent_lab.correction_harvester import record_user_correction_outcome

    record_user_correction_outcome(folder, human_turn_num)

    # HS1-3/HS1-4: per-turn trace + failure-memory preservation
    # (flag-gated, fail-open — see weakness_miner.py).
    from agent_lab.weakness_miner import write_turn_trace

    write_turn_trace(folder, human_turn_num)

    # C2: periodic L3 autonomous-mission drift audit (flag-gated, fail-open,
    # no-op unless an autonomous_segment is active — see drift_audit.py).
    from agent_lab.drift_audit import maybe_run_drift_audit

    maybe_run_drift_audit(folder, human_turn_num)

    # C3: risk-inverse profile pin — external-risk topics pin the autonomy
    # ceiling to L1 (flag-gated, fail-open — see risk_pin.py).
    from agent_lab.risk_pin import maybe_apply_risk_pin

    maybe_apply_risk_pin(folder, human_turn_num)


def _bind_session_to_run_meta(
    run_meta: RunStateLike | None,
    folder: Path | None,
) -> None:
    if not run_meta or not folder or not folder.is_dir():
        return
    from agent_lab.run.meta import stamp_run_meta

    fields: dict[str, Any] = {
        "_session_folder": str(folder.resolve()),
        "_session_id": folder.name,
    }
    from agent_lab.agent.hooks_materializer import ensure_session_agent_hooks_from_config

    manifest = ensure_session_agent_hooks_from_config(folder)
    if manifest:
        fields["agent_hooks_manifest"] = manifest
    stamp_run_meta(run_meta, **fields)


def _set_active_turn_flags(
    run_meta: RunStateLike | None,
    *,
    mode: str,
    synthesize: bool,
    consensus_mode: bool,
) -> None:
    if not run_meta:
        return
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(
        run_meta,
        _active_turn_mode=mode,
        _active_synthesize=synthesize,
        _active_consensus=consensus_mode,
    )


def _teammate_idle_peer_message(
    aid: AgentId,
    run_meta: RunStateLike | None,
    *,
    parallel_round: int,
) -> ChatMessage | None:
    if not run_meta:
        return None
    from agent_lab.room.hooks import run_teammate_idle_hooks
    from agent_lab.room.tasks import list_tasks

    agent_l = str(aid).strip().lower()
    in_prog = [t for t in list_tasks(run_meta) if t.get("owner_agent") == agent_l and t.get("status") == "in_progress"]
    folder_raw = run_meta.get("_session_folder")
    folder = Path(str(folder_raw)) if folder_raw else None
    nudge = run_teammate_idle_hooks(
        run_meta,
        agent_l,
        session_folder=folder,
        session_id=str(run_meta.get("_session_id") or ""),
        in_progress_tasks=in_prog,
    )
    if not nudge:
        return None
    return ChatMessage(
        role="system",
        agent=None,
        content=f"[idle gate · {agent_l}]\n{nudge}",
        visibility="peer",
        parallel_round=parallel_round,
    )


def _call_one_agent(
    aid: AgentId,
    *,
    topic: str,
    thread: list[ChatMessage],
    parallel_round: int,
    permissions: dict | None,
    review_mode: bool,
    review_advocate: AgentId | None,
    plan_md: str,
    run_meta: RunStateLike | None,
    on_event: OnAgentEvent | None,
    context_log: list[dict[str, Any]] | None = None,
    extra_follow_up: str = "",
    efficiency_mode: bool = False,
    slim_context: bool = False,
    human_turn_index: int = 0,
) -> ChatMessage:
    def _emit(typ: str, payload: dict[str, Any]) -> None:
        if on_event:
            on_event(typ, payload)

    _emit("agent_start", {"agent": aid, "round": parallel_round})

    folder = _session_folder_from_run_meta(run_meta)

    from agent_lab.agent.availability import (
        agent_pause_until,
        record_usage_limit_pause,
        skip_note_for_paused_agent,
    )

    paused_until = agent_pause_until(run_meta, str(aid))
    if paused_until is not None:
        note = skip_note_for_paused_agent(str(aid), reason="usage_limit")
        _emit(
            "agent_error",
            {
                "agent": aid,
                "message": note,
                "round": parallel_round,
                "failed": False,
                "non_participation": True,
                "reason": "usage_limit",
                "note": note,
                "retryable": False,
                "attempts": 0,
                "paused": True,
            },
        )
        return ChatMessage(
            role="system",
            agent=aid,
            content=note,
            parallel_round=parallel_round,
        )

    def _emit_activity_line(line: str) -> None:
        _emit(
            "agent_activity",
            {"agent": aid, "round": parallel_round, "text": line},
        )

    def _activity(line: str) -> None:
        """Legacy on_activity strings — may embed ``[tool · …]`` lines to parse."""
        from agent_lab.room.sse_stream import maybe_emit_tool_events

        _emit_activity_line(line)
        maybe_emit_tool_events(
            _emit,
            agent=str(aid),
            round=parallel_round,
            line=line,
        )

    streamed_live = False
    usage_recorded = False
    # Accumulate streamed text so a cancel can preserve the partial reply (issue D).
    streamed_parts: list[str] = []
    from agent_lab.room.sse_stream import CumulativeTextStreamer

    text_stream = CumulativeTextStreamer()

    def _bridge_event(kind: str, data: dict[str, Any]) -> None:
        nonlocal streamed_live, usage_recorded
        if kind == "text":
            piece = str(data.get("text") or "")
            if not piece:
                return
            # Claude text_delta is incremental; Kimi mapper already dedupes cumulative snapshots.
            if aid in ("claude", "kimi_work"):
                chunks = [piece]
            else:
                chunks = text_stream.feed(piece)
            for chunk in chunks:
                if not chunk:
                    continue
                streamed_live = True
                streamed_parts.append(chunk)
                _emit(
                    "agent_token",
                    {"agent": aid, "round": parallel_round, "text": chunk},
                )
            return
        if kind == "usage":
            if run_meta is not None:
                from agent_lab.cost_ledger import record_agent_usage, usage_from_bridge

                usage = usage_from_bridge(data)
                if usage is not None:
                    usage_recorded = True
                    record_agent_usage(
                        run_meta,
                        str(aid),
                        usage,
                        turn=_human_turn_number(human_turn_index),
                    )
            return
        if kind == "tool_start":
            _emit(
                "tool_start",
                {
                    "agent": aid,
                    "round": parallel_round,
                    "tool": data.get("tool", "tool"),
                    "args": data.get("args") or {},
                },
            )
            return
        if kind == "tool_output":
            _emit(
                "tool_output",
                {
                    "agent": aid,
                    "round": parallel_round,
                    "tool": data.get("tool", "tool"),
                    "chunk": data.get("chunk", ""),
                },
            )
            return
        if kind == "tool_done":
            _emit(
                "tool_done",
                {
                    "agent": aid,
                    "round": parallel_round,
                    "tool": data.get("tool", "tool"),
                },
            )
            return
        if kind == "activity":
            line = str(data.get("text") or "")
            if line:
                # Structured bridge already emits tool_* — do not re-parse activity lines.
                _emit_activity_line(line)
            return

    from agent_lab.room.messages import effective_agent_permissions

    effective_permissions = effective_agent_permissions(
        permissions,
        topic=topic,
        plan_md=plan_md,
        run_meta=run_meta,
    )

    from agent_lab.room.team_orchestration import is_discuss_only_turn, lead_discuss_role_block
    from agent_lab.room.turn_policy import (
        TurnPolicyEngine,
        TurnSignals,
        assign_task_owners_from_run_meta,
        turn_policy_enabled,
    )

    consensus_mode = bool(run_meta and run_meta.get("_active_consensus"))
    review_mode_active = review_mode
    turn_profile = str((run_meta or {}).get("turn_profile") or "").strip()
    session_id = str((run_meta or {}).get("_session_id") or "")
    human_turn = _human_turn_number(human_turn_index)

    from agent_lab.runtime.policy import PolicyEngine
    from agent_lab.room.hooks import (
        _hook_run_record,
        run_post_agent_reply_hooks,
        run_pre_agent_reply_hooks,
    )
    from agent_lab.run.meta import append_hook_run

    gate_snap = PolicyEngine.gate_snapshot(run_meta)
    from agent_lab.reply_policy import resolve_reply_policy
    from agent_lab.structured_envelope_adapter import should_request_structured_envelope

    reply_policy = resolve_reply_policy(
        parallel_round=parallel_round,
        review_mode=review_mode_active,
        consensus_mode=consensus_mode,
        turn_profile=turn_profile,
        efficiency_mode=efficiency_mode,
    )
    request_structured = should_request_structured_envelope(reply_policy)

    def _emit_hook_event(hook_result: Any, event_name: str) -> None:
        if not (hook_result.feedback.strip() or hook_result.blocked):
            return
        feedback = hook_result.feedback[:500]
        _emit(
            "hook_event",
            {
                "agent": aid,
                "event": event_name,
                "round": parallel_round,
                "blocked": hook_result.blocked,
                "feedback": feedback,
                "sub_reason": hook_result.sub_reason,
                "retryable": getattr(hook_result, "retryable", False),
            },
        )
        tag = "blocked" if hook_result.blocked else "warn"
        detail = (feedback or hook_result.sub_reason or event_name).strip()[:120]
        _activity(f"[hook · {event_name} · {tag}] {detail}")

    pre_hook = run_pre_agent_reply_hooks(
        run_meta or {},
        str(aid),
        session_folder=folder,
        session_id=session_id,
        parallel_round=parallel_round,
        consensus_mode=consensus_mode,
        review_mode=review_mode_active,
        turn_profile=turn_profile,
        gate_snapshot=gate_snap,
        human_turn=human_turn,
    )
    _emit_hook_event(pre_hook, "pre_agent_reply")
    append_hook_run(
        folder,
        _hook_run_record(
            pre_hook,
            agent=str(aid),
            session_id=session_id,
            human_turn=human_turn,
            parallel_round=parallel_round,
        ),
        run_meta=run_meta,
    )

    lead_block = ""
    if run_meta and turn_policy_enabled():
        assign = assign_task_owners_from_run_meta(run_meta)
        if assign is None:
            tp_signals = TurnSignals.from_run_meta(
                run_meta,
                consensus_meta={"status": "reached"} if consensus_mode else None,
                supervisor_first_turn=human_turn <= 1,
            )
            assign = TurnPolicyEngine.resolve(tp_signals).assign_task_owners
        if not assign and not consensus_mode:
            lead_block = lead_discuss_role_block(aid, run_meta)
    elif run_meta and is_discuss_only_turn(
        mode=str(run_meta.get("_active_turn_mode") or "discuss"),
        synthesize=bool(run_meta.get("_active_synthesize")),
        consensus_mode=consensus_mode,
    ):
        lead_block = lead_discuss_role_block(aid, run_meta)
    hook_prepend = pre_hook.feedback.strip()
    from agent_lab.plan.workflow import (
        PLAN_CLARIFY_GUIDANCE,
        build_plan_clarify_agent_block,
        plan_workflow_wants_inbox_mcp,
    )

    plan_clarify = ""
    if run_meta and folder is not None and plan_workflow_wants_inbox_mcp(run_meta):
        plan_clarify = "\n\n".join(
            x
            for x in (
                PLAN_CLARIFY_GUIDANCE,
                build_plan_clarify_agent_block(folder, agent_id=str(aid), run_meta=run_meta),
            )
            if x and x.strip()
        )
    combined_follow = "\n\n".join(
        x for x in (lead_block, hook_prepend, plan_clarify, extra_follow_up) if x and x.strip()
    )

    def _invoke_agent(payload: str) -> tuple[str, Any, dict[str, Any] | None, str, Any]:
        from agent_lab.agents.registry import call_agent_reply
        from agent_lab.cursor.inbox_mcp import discuss_inbox_mcp_enabled

        # Loop discuss + plan-workflow CLARIFY share discuss_inbox_mcp_enabled (not execute).
        use_inbox_mcp = discuss_inbox_mcp_enabled(run_meta, agent_id=str(aid))
        perms = dict(effective_permissions or {})
        if use_inbox_mcp:
            perms["_inbox_caller_agent"] = str(aid)
            perms["_inbox_policy_lane"] = "discuss"
        agent_reply = call_agent_reply(
            aid,
            "",
            payload,
            permissions=perms,
            on_activity=_activity,
            on_bridge_event=_bridge_event,
            session_folder=folder,
            request_structured_envelope=request_structured,
            inbox_mcp=use_inbox_mcp,
        )
        text = agent_reply.text
        parsed = parse_agent_response_v2(
            text,
            structured=agent_reply.structured_envelope,
        )
        envelope_dict = parsed.envelope.to_dict() if parsed.envelope else None
        body = parsed.body or text
        post_hook = run_post_agent_reply_hooks(
            run_meta or {},
            str(aid),
            content=body,
            envelope=envelope_dict,
            envelope_parse_error=parsed.envelope_parse_error,
            session_folder=folder,
            session_id=session_id,
            parallel_round=parallel_round,
            consensus_mode=consensus_mode,
            review_mode=review_mode_active,
            turn_profile=turn_profile,
            gate_snapshot=gate_snap,
            human_turn=human_turn,
        )
        append_hook_run(
            folder,
            _hook_run_record(
                post_hook,
                agent=str(aid),
                session_id=session_id,
                human_turn=human_turn,
                parallel_round=parallel_round,
            ),
            run_meta=run_meta,
        )
        _emit_hook_event(post_hook, "post_agent_reply")
        return text, parsed, envelope_dict, body, post_hook

    try:
        bundle = build_agent_context_bundle(
            topic,
            thread,
            aid,
            permissions=permissions,
            parallel_round=parallel_round,
            review_mode=review_mode,
            review_advocate=review_advocate,
            plan_md=plan_md,
            run_meta=run_meta,
            efficiency_mode=efficiency_mode,
            slim_context=slim_context,
            consensus_mode=consensus_mode,
        )
        payload = bundle.render()
        if combined_follow.strip():
            payload = f"{payload}\n\n{combined_follow.strip()}"
        context_meta = bundle.meta.to_dict()
        context_meta["model"] = __import__("agent_lab.room", fromlist=["model_label"]).model_label(aid)
        from agent_lab.context.meta import apply_invoke_follow_to_context_meta

        apply_invoke_follow_to_context_meta(context_meta, combined_follow)
        if context_log is not None:
            context_log.append(context_meta)
            if run_meta is not None:
                from agent_lab.token_budget import record_run_token_budget

                record_run_token_budget(run_meta, context_log, turn_meta=context_meta)

        text, parsed, envelope_dict, body, post_hook = _invoke_agent(payload)
        needs_envelope_fix = reply_policy.envelope_strict and (parsed.envelope_parse_error or parsed.envelope is None)
        if consensus_mode and ((post_hook.blocked and post_hook.retryable) or needs_envelope_fix):
            if post_hook.blocked and post_hook.feedback.strip():
                retry_follow = f"[Hook — envelope/format fix required]\n{post_hook.feedback.strip()}"
            else:
                retry_follow = (
                    "[Envelope required — consensus R2+]\n"
                    "Reply must start with ```agent-envelope fenced JSON "
                    '({"act":"ENDORSE",...}) then your body.'
                )
            retry_payload = f"{payload}\n\n{retry_follow}"
            text, parsed, envelope_dict, body, post_hook = _invoke_agent(retry_payload)

        from agent_lab.room.chat_channels import (
            message_visibility,
            strip_peer_header_echo,
            strip_sdk_internal_monologue,
        )

        # Some agents (often the lead, which sees the most peer context) prepend
        # the "[이번 턴 · 동료 발화]" header to their reply; left in, the whole
        # message is classified peer-only and vanishes from the transcript.
        body = strip_peer_header_echo(body)
        body = strip_sdk_internal_monologue(body)
        if streamed_live and streamed_parts:
            from agent_lab.room.sse_stream import choose_agent_reply_body

            body = choose_agent_reply_body(
                streamed="".join(streamed_parts),
                final_body=body,
            )

        msg = ChatMessage(
            role="agent",
            agent=aid,
            content=body,
            parallel_round=parallel_round,
            envelope=envelope_dict,
            visibility=message_visibility(role="agent", content=body),
            envelope_parse_error=parsed.envelope_parse_error,
        )
        if parallel_round >= 2 and (consensus_mode or review_mode_active):
            if parsed.envelope_parse_error:
                _activity("[envelope · parse_error] R2+ fence/JSON invalid")
            elif not (envelope_dict or {}).get("act"):
                _activity("[envelope · missing] R2+ act required")
        from agent_lab.room.sse_stream import emit_agent_tokens

        if not streamed_live:
            emit_agent_tokens(
                _emit,
                agent=str(aid),
                round=parallel_round,
                text=body,
            )
        _emit(
            "agent_done",
            {
                "agent": aid,
                "chars": len(body),
                "content": body,
                "round": parallel_round,
                "pass": is_pass_reply(body, envelope_dict),
                "no_objection": is_endorse_reply(body, envelope_dict),
                "envelope": envelope_dict,
                "envelope_valid": parsed.envelope is not None,
                "envelope_parse_error": parsed.envelope_parse_error,
                "context_meta": context_meta,
                "hook_blocked": post_hook.blocked,
            },
        )
        if folder and msg.role == "agent":
            from agent_lab.run.meta import record_completed_step

            record_completed_step(
                folder,
                human_turn=human_turn,
                parallel_round=parallel_round,
                agent=str(aid),
                content=body,
                envelope=envelope_dict,
                run_meta=run_meta,
            )
            from agent_lab.mission.board import record_agent_call

            record_agent_call(
                folder,
                human_turn=human_turn,
                agent=str(aid),
                run_meta=run_meta,
            )
            if run_meta is not None:
                from agent_lab.cost_ledger import (
                    estimate_usage_from_text,
                    persist_cost_ledger,
                    record_agent_usage,
                )

                if not usage_recorded:
                    model = str(context_meta.get("model") or "") or None
                    est = estimate_usage_from_text(
                        input_chars=len(payload),
                        output_chars=len(body),
                        model=model,
                    )
                    if est.tokens_in or est.tokens_out:
                        record_agent_usage(
                            run_meta,
                            str(aid),
                            est,
                            turn=human_turn,
                        )
                persist_cost_ledger(folder, run_meta)
                if context_log is not None and run_meta is not None:
                    ledger = run_meta.get("cost_ledger")
                    if isinstance(ledger, dict):
                        by_agent = ledger.get("by_agent")
                        if isinstance(by_agent, dict):
                            agent_entry = by_agent.get(str(aid))
                            if isinstance(agent_entry, dict):
                                context_meta["usage_cache_read"] = int(agent_entry.get("cache_read") or 0)
                    from agent_lab.token_budget import record_run_token_budget

                    record_run_token_budget(run_meta, context_log, turn_meta=context_meta)
        return msg
    except Exception as e:
        if isinstance(e, RoomRunCancelled) or is_cancelled():
            # Preserve whatever the agent streamed before ⌘. instead of wiping it
            # with "[X error] run cancelled by user" (issue D).
            partial = "".join(streamed_parts).strip()
            body = f"{partial}\n\n_(취소됨)_" if partial else "_(취소됨)_"
            _emit(
                "agent_done",
                {
                    "agent": aid,
                    "chars": len(partial),
                    "content": body,
                    "round": parallel_round,
                    "cancelled": True,
                },
            )
            return ChatMessage(
                role="agent" if partial else "system",
                agent=aid,
                content=body,
                parallel_round=parallel_round,
            )
        reason = _non_participation_reason(e)
        error_note: str | None = None
        if reason == "usage_limit":
            record_usage_limit_pause(str(aid), run_meta=run_meta, error=e)
            error_note = skip_note_for_paused_agent(str(aid), reason="usage_limit")
        elif reason:
            error_note = skip_note_for_paused_agent(str(aid), reason=reason)
        retryable = retryable_failure(e) or is_retryable(str(e))
        attempts = retry_attempts(e)
        _emit(
            "agent_error",
            {
                "agent": aid,
                "message": str(e),
                "round": parallel_round,
                "failed": not bool(reason),
                "non_participation": bool(reason),
                "reason": reason,
                "note": error_note,
                "retryable": retryable,
                "attempts": attempts,
            },
        )
        if error_note:
            return ChatMessage(
                role="system",
                agent=aid,
                content=error_note,
                parallel_round=parallel_round,
            )
        return ChatMessage(
            role="system",
            agent=aid,
            content=f"[{agent_label(aid)} error] {e}",
            parallel_round=parallel_round,
        )
