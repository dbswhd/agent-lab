"""Plan synthesis and scribe workflow helpers."""

from __future__ import annotations

from agent_lab.room._typing import agent_label
import os
from pathlib import Path
from typing import Any, Callable, cast

from agent_lab.run.state import RunStateLike

from agent_lab.agents.prompts import room_scribe_prompt
from agent_lab.agents.registry import AGENT_IDS, AgentId, AgentReply, available_agents
from agent_lab.session import SESSIONS_DIR, session_dir
from agent_lab.room.messages import (
    ChatMessage,
    OnAgentEvent,
    _human_turn_count,
)


def format_thread_numbered(messages: list[ChatMessage]) -> str:
    """Thread with chat.jsonl line numbers for scribe provenance."""
    lines: list[str] = []
    for i, m in enumerate(messages, start=1):
        if m.role == "user":
            lines.append(f"L{i} Human:\n{m.content}\n")
        elif m.role == "agent" and m.agent:
            lines.append(f"L{i} {agent_label(m.agent)}:\n{m.content}\n")
        else:
            lines.append(f"L{i} System:\n{m.content}\n")
    return "\n".join(lines)


def synthesize_plan(
    topic: str,
    messages: list[ChatMessage],
    backend_agent: AgentId | None = None,
    *,
    run_meta: RunStateLike | None = None,
) -> str:
    """Scribe pass using one agent backend."""
    from agent_lab.room.context import scribe_thread_block
    from agent_lab.room.scribe_enrichment import (
        build_scribe_enrichment,
        format_scribe_agent_summaries_block,
    )

    agent: AgentId = backend_agent or _default_scribe_agent()
    latest_human = ""
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user >= 0:
        latest_human = (messages[last_user].content or "").strip()

    summaries_block = format_scribe_agent_summaries_block(messages, run_meta)
    if summaries_block.strip():
        agent_input = summaries_block
    else:
        numbered = scribe_thread_block(cast(Any, messages))
        agent_input = (
            f"Numbered conversation (fallback — no agent replies; use L{{n}} as chat.jsonl#L{{n}} refs):\n\n{numbered}"
        )

    user = (
        f"Human topic:\n{topic.strip()}\n\n"
        f"---\n\nLatest human message:\n{latest_human or '(none)'}\n\n"
        f"---\n\n{agent_input}\n\n---\n\nWrite the final plan.md content."
    )
    cycles = (run_meta or {}).get("plan_cycles") or []
    if cycles:
        user = (
            f"{user}\n\n"
            "This is a new plan cycle — write a fresh plan scoped to the current "
            "human topic only. Do not carry forward sections from archived prior plans."
        )
    enrichment = build_scribe_enrichment(run_meta, messages)
    if enrichment.strip():
        user = f"{user}\n\n---\n\n{enrichment.strip()}"
    folder_raw = (run_meta or {}).get("_session_folder")
    if folder_raw:
        from agent_lab.plan.workflow import build_clarify_context_block

        clarify_block = build_clarify_context_block(Path(str(folder_raw)))
        if clarify_block.strip():
            user = f"{user}\n\n---\n\n{clarify_block.strip()}"
    room = __import__("agent_lab.room", fromlist=["call_agent"])
    folder_raw = (run_meta or {}).get("_session_folder")
    folder = Path(str(folder_raw)) if folder_raw else None
    if folder is not None and folder.is_dir():
        from agent_lab.agents.registry import call_agent_reply
        from agent_lab.sidecar_accounting import tracked_agent_call

        reply = tracked_agent_call(
            folder,
            str(agent),
            kind="scribe",
            fn=lambda bridge: call_agent_reply(
                agent,
                room_scribe_prompt(run_meta),
                user,
                scribe=True,
                on_bridge_event=bridge,
            ),
        )
        return reply.text if isinstance(reply, AgentReply) else str(reply)
    result = room.call_agent(agent, room_scribe_prompt(run_meta), user, scribe=True)
    return str(result)


def auto_plan_scribe_enabled() -> bool:
    """Every completed turn re-synthesizes plan.md (disable via AGENT_LAB_AUTO_PLAN_SCRIBE=0)."""
    raw = os.getenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _should_scribe_plan_after_turn(
    *,
    synthesize: bool,
    cancelled: bool,
    run_meta: RunStateLike | None = None,
    user_plan_send: bool = False,
) -> bool:
    if cancelled:
        return False
    from agent_lab.plan.workflow import (
        is_plan_workflow_active,
        plan_workflow_allows_auto_scribe,
        plan_workflow_allows_scribe,
    )

    if is_plan_workflow_active(run_meta):
        return plan_workflow_allows_scribe(
            run_meta,
            synthesize=synthesize,
            user_plan_send=user_plan_send,
        )
    return synthesize or plan_workflow_allows_auto_scribe(run_meta)


def _plan_trigger_for_turn(*, synthesize: bool, scribe_applied: bool) -> str | None:
    if not scribe_applied:
        return None
    return "plan_turn" if synthesize else "auto_turn"


def _read_plan_before(folder: Path | None) -> str:
    if folder is None:
        return ""
    from agent_lab.plan.paths import read_session_plan_md
    from agent_lab.run.meta import read_run_meta

    return read_session_plan_md(folder, read_run_meta(folder))


def _bootstrap_session_folder_for_plan_workflow(
    topic: str,
    *,
    base: Path | None,
    synthesize: bool,
) -> Path | None:
    """Create on-disk session folder before first agent round (plan workflow needs run.json)."""
    from agent_lab.plan.workflow import (
        init_plan_workflow_on_plan_send,
        should_enable_plan_workflow,
    )

    if not should_enable_plan_workflow(synthesize=synthesize):
        return None
    folder = session_dir(topic, base=base or SESSIONS_DIR)
    (folder / "topic.txt").write_text(topic.strip() + "\n", encoding="utf-8")
    from agent_lab.run.meta import write_run_meta

    write_run_meta(folder, {"topic": topic})
    init_plan_workflow_on_plan_send(folder)
    return folder


def _plan_workflow_post_agent_turn(
    folder: Path,
    *,
    topic: str,
    messages: list[ChatMessage],
    run_meta: RunStateLike,
    plan_before: str,
    mode: str,
    synthesize: bool,
    cancelled: bool,
    active_agents: list[Any],
    permissions: dict | None,
    on_event: OnAgentEvent | None,
) -> tuple[str, bool, dict[str, Any]]:
    """Tick plan FSM, optional scribe, peer-review pipeline after agent replies."""
    from agent_lab.human_inbox import has_pending_question
    from agent_lab.plan.workflow import (
        emit_plan_workflow_phase_if_changed,
        is_plan_workflow_active,
        orchestrate_plan_workflow_pipeline,
        plan_workflow_phase,
        plan_workflow_should_advance_on_turn,
        tick_plan_workflow_after_turn,
    )
    from agent_lab.run.meta import read_run_meta

    # S1 fix: the plan-FSM reloads below (_session_context / read_run_meta) return
    # a fresh run_meta from disk, dropping ephemeral turn keys that were never
    # persisted (_turn_category / _turn_roles set by run_consensus_agent_rounds).
    # Capture them now and carry forward so the turn snapshot still records the
    # route category + role plan (feeds turn_metrics → outcomes ledger).
    _ephemeral_turn = {k: run_meta.get(k) for k in ("_turn_category", "_turn_roles") if run_meta.get(k) is not None}

    plan_md = plan_before
    pw_force_scribe = False
    pw_active = is_plan_workflow_active(run_meta)
    pw_advance = plan_workflow_should_advance_on_turn(run_meta, synthesize=synthesize)
    phase_before = plan_workflow_phase(run_meta) if pw_active else None
    from agent_lab.room.turn_policy import turn_policy_enabled

    if turn_policy_enabled():
        plan_md = plan_before
        scribe_applied = False
    elif pw_active and pw_advance and not cancelled:
        from agent_lab.room.agent_invoke import _bind_session_to_run_meta
        from agent_lab.room.session_persist import _session_context

        pw_tick = tick_plan_workflow_after_turn(
            folder,
            synthesize=synthesize,
            cancelled=cancelled,
            plan_md=plan_md,
            plan_before=plan_before,
            has_pending_inbox_question=has_pending_question(run_meta),
        )
        if pw_tick.get("wait_inbox") and on_event:
            on_event("inbox_pending", {"phase": "CLARIFY"})
        if pw_tick.get("advance") == "DRAFT":
            pw_force_scribe = True
        plan_md, run_meta = _session_context(folder)
        _bind_session_to_run_meta(run_meta, folder)

    if not turn_policy_enabled():
        scribe_applied = (
            _should_scribe_plan_after_turn(
                synthesize=synthesize,
                cancelled=cancelled,
                run_meta=run_meta,
                user_plan_send=synthesize,
            )
            or pw_force_scribe
        )
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
    elif pw_force_scribe:
        scribe_applied = False
    # Auto-advance: if plan_workflow is already in DRAFT and scribe changed plan.md,
    # drive PEER_REVIEW without requiring synthesize=True (user turn not needed).
    _auto_draft_advance = (
        not pw_advance
        and scribe_applied
        and plan_md != plan_before
        and is_plan_workflow_active(run_meta)
        and plan_workflow_phase(read_run_meta(folder)) == "DRAFT"
    )
    if (pw_advance or _auto_draft_advance) and is_plan_workflow_active(run_meta) and not cancelled and scribe_applied:
        plan_md, pw_replies, pw_meta = orchestrate_plan_workflow_pipeline(
            folder,
            topic=topic,
            messages=messages,
            plan_md=plan_md,
            plan_before=plan_before,
            synthesize=synthesize or _auto_draft_advance,
            cancelled=cancelled,
            agents=[str(a) for a in active_agents],
            permissions=permissions,
            run_meta=run_meta,
            on_event=on_event,
        )
        if pw_replies:
            messages.extend(pw_replies)
        if pw_meta.get("pending_approval") and on_event:
            on_event(
                "plan_workflow_pending",
                {"phase": plan_workflow_phase(read_run_meta(folder))},
            )
    if pw_active:
        run_meta = read_run_meta(folder)
        emit_plan_workflow_phase_if_changed(
            folder,
            on_event,
            phase_before,
            plan_workflow_phase(run_meta),
        )
    # Restore ephemeral turn keys lost to the disk reloads above (S1 fix).
    for key, value in _ephemeral_turn.items():
        run_meta.setdefault(key, value)
    return plan_md, scribe_applied, run_meta


def _apply_scribe_after_turn(
    *,
    topic: str,
    messages: list[ChatMessage],
    run_meta: RunStateLike | None,
    plan_before: str,
    mode: str,
    scribe: bool,
    user_plan_send: bool,
    cancelled: bool,
    on_event: OnAgentEvent | None,
    session_folder: Path | None = None,
    plan_trigger: str | None = None,
) -> str:
    """Run scribe, patch objections only (E2b), or leave plan unchanged."""
    if not scribe or cancelled:
        return plan_before
    if not messages:
        return plan_before
    from agent_lab.room.scribe_enrichment import (
        patch_plan_objections_only,
        should_skip_scribe_for_open_objections,
    )

    if should_skip_scribe_for_open_objections(run_meta, mode=mode, synthesize=user_plan_send):
        if on_event:
            on_event("scribe_skipped", {"reason": "open_objections_discuss"})
        return patch_plan_objections_only(plan_before, run_meta)
    if session_folder and run_meta is not None:
        from agent_lab.room.hooks import _hook_run_record, run_pre_scribe_hooks
        from agent_lab.run.meta import append_hook_run

        pre = run_pre_scribe_hooks(
            run_meta,
            session_folder=session_folder,
            session_id=str(run_meta.get("_session_id") or session_folder.name),
            trigger=plan_trigger or ("plan_turn" if user_plan_send else "auto_turn"),
            message_count=len(messages),
        )
        append_hook_run(
            session_folder,
            _hook_run_record(
                pre,
                session_id=str(run_meta.get("_session_id") or session_folder.name),
                human_turn=_human_turn_count(messages),
            ),
            run_meta=run_meta,
        )
        if pre.blocked:
            msg = pre.feedback.strip() or "pre_scribe hook blocked plan synthesis"
            if on_event:
                on_event("scribe_error", {"message": msg, "hook": "pre_scribe"})
            if not (plan_before or "").strip():
                return f"## Plan synthesis blocked\n\n{msg}"
            return plan_before
    if on_event:
        on_event("scribe_start", {})
    try:
        room = __import__("agent_lab.room", fromlist=["synthesize_plan"])
        plan_md = room.synthesize_plan(topic, messages, run_meta=run_meta)
        _emit_plan_actions_validation(plan_md, on_event)
        if on_event:
            on_event("scribe_done", {"chars": len(plan_md)})
        return cast(str, plan_md)
    except Exception as e:
        if on_event:
            on_event("scribe_error", {"message": str(e)})
        if not (plan_before or "").strip():
            return f"## Plan synthesis failed\n\n{e}"
        return plan_before


def _default_scribe_agent() -> AgentId:
    raw = (os.getenv("ROOM_SCRIBE_AGENT") or "claude").strip().lower()
    if raw in AGENT_IDS and raw in available_agents():
        return raw  # type: ignore[return-value]
    for fallback in ("codex", "claude", "cursor"):
        if fallback in available_agents():
            return fallback  # type: ignore[return-value]
    return "claude"


def _emit_plan_actions_validation(
    plan_md: str,
    on_event: Callable[[str, dict[str, Any]], None] | None,
) -> dict[str, Any]:
    import logging

    from agent_lab.plan.actions import validate_plan_actions_format

    result = validate_plan_actions_format(plan_md)
    if on_event:
        on_event("plan_actions_validation", result)
    if not result.get("ok"):
        logging.getLogger("agent_lab.plan.actions").warning(
            "plan_actions_validation issues=%s",
            result.get("issues"),
        )
    return result
