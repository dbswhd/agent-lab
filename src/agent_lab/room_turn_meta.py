"""Turn snapshots, plan sync, and post-turn orchestration hooks."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agent_lab.agents.registry import available_agents
from agent_lab.context_meta import summarize_turn_context
from agent_lab.consensus_agreements import (
    mark_agreements_plan_synced,
)
from agent_lab.room_messages import (
    ChatMessage,
    OnAgentEvent,
    _human_turn_count,
    _now,
)


from agent_lab.room_plan_scribe import (
    _emit_plan_actions_validation,
    synthesize_plan,
)

from agent_lab.room_session_persist import (
    _find_completed_synthesize,
    _read_run_meta,
    _write_session_files,
    load_session_messages,
)


def _peer_metrics_for_messages(messages: list[ChatMessage]) -> dict[str, Any]:
    from agent_lab.room_turn_state import current_turn_slice, peer_turn_metrics

    turn_msgs, _ = current_turn_slice(messages)
    return peer_turn_metrics(turn_msgs)


def _final_turn_state_dict(
    messages: list[ChatMessage],
    *,
    run_meta: dict[str, Any] | None,
    active_agents: list[str],
    consensus_meta: dict[str, Any] | None,
    plan_md: str,
) -> dict[str, Any]:
    if run_meta and run_meta.get("turn_state"):
        return run_meta["turn_state"]  # type: ignore[return-value]
    from agent_lab.room_turn_state import current_turn_slice, derive_turn_state

    turn_msgs, line_base = current_turn_slice(messages)
    return derive_turn_state(
        turn_msgs,
        line_base=line_base,
        active_agents=active_agents,
        consensus=consensus_meta,
        plan_md=plan_md,
    ).to_dict()


def _turn_snapshot(
    *,
    mode: str,
    synthesize: bool,
    agents_used: list[str],
    parallel_rounds: int,
    permissions: dict | None,
    latency_ms: int,
    status: str = "completed",
    synthesize_only: bool = False,
    plan_trigger: str | None = None,
    request_id: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    review_mode: bool = False,
    review_advocate: str | None = None,
    context_log: list[dict[str, Any]] | None = None,
    consensus_mode: bool = False,
    consensus: dict[str, Any] | None = None,
    efficiency_mode: bool = False,
    turn_state: dict[str, Any] | None = None,
    turn_profile: str | None = None,
    plan_sync_summary: str | None = None,
    turn_lead: str | None = None,
    turn_leads: dict[str, str] | None = None,
    send_receipt: str | None = None,
    peer_message_count: int | None = None,
    agents_with_r2_reply: list[str] | None = None,
    failed_agents: list[str] | None = None,
    succeeded_agents: list[str] | None = None,
    last_delegate: dict[str, Any] | None = None,
    communicate_meta: dict[str, Any] | None = None,
    category: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from agent_lab.invoke import model_name

    snap: dict[str, Any] = {
        "mode": mode,
        "synthesize": synthesize,
        "agent_parallel_rounds": parallel_rounds,
        "agents": agents_used,
        "permissions": permissions or {},
        "model": model_name(),
        "latency_ms": latency_ms,
        "status": status,
    }
    if context_log:
        snap["context"] = {
            "agents": context_log,
            "payload_chars_total": sum((entry.get("layer_chars") or {}).get("total", 0) for entry in context_log),
            "summary": summarize_turn_context(context_log),
        }
        snap["models"] = {entry["agent"]: entry.get("model", "") for entry in context_log if entry.get("agent")}
    if synthesize_only:
        snap["synthesize_only"] = True
    if plan_trigger:
        snap["plan_trigger"] = plan_trigger
    if request_id:
        snap["request_id"] = request_id
    if started_at:
        snap["started_at"] = started_at
    if completed_at:
        snap["completed_at"] = completed_at
    if review_mode:
        snap["review_mode"] = True
        if review_advocate:
            snap["review_advocate"] = review_advocate
    if consensus_mode:
        snap["consensus_mode"] = True
        if consensus:
            snap["consensus"] = consensus
    if efficiency_mode:
        snap["efficiency_mode"] = True
    if turn_state:
        snap["turn_state"] = turn_state
    if turn_profile and turn_profile in (
        "quick",
        "analyze",
        "discuss",
        "review",
        "free",
        "specialist",
        "verified",
    ):
        snap["turn_profile"] = "analyze" if turn_profile == "discuss" else turn_profile
    if plan_sync_summary:
        snap["plan_sync_summary"] = plan_sync_summary
    if turn_lead:
        snap["turn_lead"] = turn_lead
    if turn_leads:
        snap["turn_leads"] = turn_leads
    if send_receipt:
        snap["send_receipt"] = send_receipt
    if peer_message_count is not None:
        snap["peer_message_count"] = peer_message_count
    if agents_with_r2_reply:
        snap["agents_with_r2_reply"] = list(agents_with_r2_reply)
    if failed_agents:
        snap["failed_agents"] = list(failed_agents)
    if succeeded_agents:
        snap["succeeded_agents"] = list(succeeded_agents)
    if last_delegate:
        snap["last_delegate"] = dict(last_delegate)
    if communicate_meta:
        snap["communicate_meta"] = communicate_meta
    if category:
        snap["category"] = dict(category)
    return snap


def consensus_reached(consensus_meta: dict[str, Any] | None) -> bool:
    """True when free-discuss consensus loop finished with full agreement."""
    return bool(consensus_meta and consensus_meta.get("status") == "reached")


def _post_plan_scribe_inbox_harvest(
    folder: Path,
    *,
    plan_md: str,
    trigger: str,
    verified_at: str | None = None,
    verified_excerpt: str | None = None,
    verified_summary: str | None = None,
) -> None:
    """After auto plan scribe: T-Q2 + T-B1 inbox harvest (discuss-mode gates)."""
    from agent_lab.inbox_harvest import (
        _supersede_legacy_verified_build_items,
        harvest_post_plan_inbox,
    )
    from agent_lab.run_meta import patch_run_meta

    messages = load_session_messages(folder)
    human_turn = _human_turn_count(messages)

    def _patch(run_meta: dict[str, Any]) -> dict[str, Any]:
        if trigger == "verified_loop_done":
            _supersede_legacy_verified_build_items(run_meta)
        harvest_post_plan_inbox(
            run_meta,
            messages,
            plan_md=plan_md,
            human_turn=human_turn,
        )
        if trigger == "verified_loop_done" and verified_at:
            run_meta["verified_plan_sync"] = {
                "verified_at": verified_at,
                "summary": verified_summary or "",
                "excerpt": verified_excerpt or "",
                "ts": _now(),
            }
        from agent_lab.human_inbox import compute_inbox_pending

        run_meta["inbox_pending"] = compute_inbox_pending(run_meta)
        return run_meta

    patch_run_meta(folder, _patch)

    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.runtime import dispatch

    dispatch(folder, RuntimeEvent.SCRIBE_COMPLETE, {"plan_md": plan_md})


def _emit_plan_pipeline_proposal(
    folder: Path,
    *,
    excerpt: str,
    summary: str,
    notice: str,
    permissions: dict | None,
    on_event: OnAgentEvent | None,
    trigger: str,
) -> None:
    if not on_event:
        return
    synced_event = "verified_plan_synced" if trigger == "verified_loop_done" else "consensus_plan_synced"
    on_event(
        synced_event,
        {
            "excerpt": excerpt,
            "summary": summary,
            "notice": notice,
            "trigger": trigger,
        },
    )
    from agent_lab.runtime.invoke_execute import list_plan_actions

    actions_info = list_plan_actions(folder, permissions=permissions)
    recommended = actions_info.get("recommended")
    has_executable = recommended is not None
    action_key = recommended.get("action_key") if recommended else None
    on_event(
        "consensus_dry_run_proposal",
        {
            "excerpt": excerpt,
            "summary": summary,
            "notice": notice,
            "recommended": recommended,
            "has_executable": has_executable,
            "action_key": action_key,
            "trigger": trigger,
        },
    )


def synthesize_session_plan(
    folder: Path,
    *,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    request_id: str | None = None,
    trigger: str = "synthesize_only",
    previous_plan_md: str | None = None,
) -> tuple[str, str]:
    """Re-synthesize plan.md from existing chat without a new agent round."""
    from agent_lab.plan_sync_summary import summarize_plan_changes

    if not folder.is_dir():
        raise FileNotFoundError(f"session not found: {folder}")
    plan_path = folder / "plan.md"
    old_plan = previous_plan_md
    if old_plan is None and plan_path.is_file():
        old_plan = plan_path.read_text(encoding="utf-8")
    if request_id and _find_completed_synthesize(folder, request_id):
        if plan_path.is_file():
            if on_event:
                on_event("scribe_skipped", {"reason": "duplicate_request_id"})
            current = plan_path.read_text(encoding="utf-8")
            return current, summarize_plan_changes(old_plan or "", current)
        raise FileNotFoundError("plan.md not found")
    topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
    messages = load_session_messages(folder)
    if not messages:
        raise ValueError("no messages to synthesize")
    started_at = _now()
    t0 = time.perf_counter()
    run_meta_snapshot = _read_run_meta(folder)
    from agent_lab.room_hooks import _hook_run_record, run_pre_scribe_hooks
    from agent_lab.run_meta import append_hook_run

    pre = run_pre_scribe_hooks(
        run_meta_snapshot,
        session_folder=folder,
        session_id=folder.name,
        trigger=trigger,
        message_count=len(messages),
    )
    append_hook_run(
        folder,
        _hook_run_record(pre, session_id=folder.name),
        run_meta=run_meta_snapshot,
    )
    if pre.blocked:
        msg = pre.feedback.strip() or "pre_scribe hook blocked plan synthesis"
        if on_event:
            on_event("scribe_error", {"message": msg, "hook": "pre_scribe"})
        raise RuntimeError(msg)
    if on_event:
        on_event("scribe_start", {})
    try:
        plan_md = synthesize_plan(topic, messages, run_meta=_read_run_meta(folder))
        _emit_plan_actions_validation(plan_md, on_event)
        if on_event:
            on_event("scribe_done", {"chars": len(plan_md)})
    except Exception as e:
        if on_event:
            on_event("scribe_error", {"message": str(e)})
        raise
    plan_sync_summary = summarize_plan_changes(old_plan or "", plan_md)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    completed_at = _now()
    existing_meta: dict[str, Any] = {}
    meta_path = folder / "meta.json"
    if meta_path.is_file():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    agents_used = existing_meta.get("agents") or [a for a in available_agents()]
    _write_session_files(
        folder,
        topic,
        messages,
        plan_md,
        agents_used=agents_used,
        merge_meta={**existing_meta, "topic": topic},
        turn_meta=_turn_snapshot(
            mode="plan",
            synthesize=True,
            agents_used=agents_used,
            parallel_rounds=0,
            permissions=permissions,
            latency_ms=latency_ms,
            synthesize_only=True,
            plan_trigger=trigger,
            request_id=request_id,
            started_at=started_at,
            completed_at=completed_at,
            plan_sync_summary=plan_sync_summary,
            send_receipt="plan_updated",
        ),
    )
    return plan_md, plan_sync_summary


def maybe_auto_scribe_after_consensus(
    folder: Path,
    *,
    consensus_meta: dict[str, Any] | None,
    synthesize: bool,
    cancelled: bool,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
) -> str | None:
    """After discuss+consensus, auto-scribe plan.md and notify what was reflected."""
    from agent_lab.consensus_agreements import (
        agreement_plan_synced_notice,
        consensus_topic_excerpt,
    )

    if cancelled or not consensus_reached(consensus_meta):
        return None

    excerpt = consensus_topic_excerpt(consensus_meta)
    plan_path = folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""

    from agent_lab.consensus_agreements import pending_consensus_agreements
    from agent_lab.run_meta import read_run_meta

    run = read_run_meta(folder)
    pending = pending_consensus_agreements(run.get("consensus_agreements"))
    if not pending:
        if plan_md.strip():
            return plan_md
        return None

    if on_event:
        on_event("consensus_plan_sync_start", {"excerpt": excerpt})

    old_plan = plan_md
    try:
        room = __import__("agent_lab.room", fromlist=["synthesize_session_plan"])
        plan_md, summary = room.synthesize_session_plan(
            folder,
            on_event=on_event,
            permissions=permissions,
            trigger="consensus_reached",
            previous_plan_md=old_plan,
        )
        current_plan = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
        if current_plan != plan_md:
            plan_path.write_text(plan_md, encoding="utf-8")
    except Exception as e:
        if on_event:
            on_event(
                "consensus_plan_sync_failed",
                {"excerpt": excerpt, "message": str(e)},
            )
            on_event(
                "scribe_error",
                {"message": str(e), "auto": True, "excerpt": excerpt},
            )
        return None

    _post_plan_scribe_inbox_harvest(
        folder,
        plan_md=plan_md,
        trigger="consensus_reached",
    )

    from agent_lab.run_meta import patch_run_meta

    messages = load_session_messages(folder)

    def _mark_agreements_synced(run_meta: dict[str, Any]) -> dict[str, Any]:
        run_meta["consensus_agreements"] = mark_agreements_plan_synced(
            run_meta.get("consensus_agreements"),
            message_count=len(messages),
            synced_at=_now(),
        )
        return run_meta

    patch_run_meta(folder, _mark_agreements_synced)

    notice = agreement_plan_synced_notice(excerpt, summary)
    _emit_plan_pipeline_proposal(
        folder,
        excerpt=excerpt,
        summary=summary,
        notice=notice,
        permissions=permissions,
        on_event=on_event,
        trigger="consensus_reached",
    )
    return plan_md


def maybe_auto_scribe_after_verified_loop(
    folder: Path,
    *,
    verified_result: dict[str, Any] | None,
    cancelled: bool,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
) -> str | None:
    """After Oracle VERIFIED, auto-scribe plan.md then harvest Question + Build."""
    from agent_lab.consensus_agreements import agreement_plan_synced_notice
    from agent_lab.run_meta import read_run_meta

    if cancelled or not verified_result:
        return None
    loop = dict(verified_result.get("verified_loop") or {})
    if str(loop.get("status") or "") != "done":
        return None

    verified_at = str(loop.get("verified_at") or "").strip()
    run = read_run_meta(folder)
    sync = dict(run.get("verified_plan_sync") or {})
    if sync.get("verified_at") == verified_at:
        return None

    loop_goal = dict(loop.get("loop_goal") or {})
    excerpt = str(loop_goal.get("text") or "").strip()[:200] or "Verified loop"

    plan_path = folder / "plan.md"
    old_plan = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""

    if on_event:
        on_event("verified_plan_sync_start", {"excerpt": excerpt})

    try:
        room = __import__("agent_lab.room", fromlist=["synthesize_session_plan"])
        plan_md, summary = room.synthesize_session_plan(
            folder,
            on_event=on_event,
            permissions=permissions,
            trigger="verified_loop_done",
            previous_plan_md=old_plan,
        )
        current_plan = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
        if current_plan != plan_md:
            plan_path.write_text(plan_md, encoding="utf-8")
    except Exception as e:
        if on_event:
            on_event(
                "verified_plan_sync_failed",
                {"excerpt": excerpt, "message": str(e)},
            )
            on_event(
                "scribe_error",
                {
                    "message": str(e),
                    "auto": True,
                    "excerpt": excerpt,
                    "trigger": "verified_loop_done",
                },
            )
        return None

    _post_plan_scribe_inbox_harvest(
        folder,
        plan_md=plan_md,
        trigger="verified_loop_done",
        verified_at=verified_at,
        verified_excerpt=excerpt,
        verified_summary=summary,
    )

    notice = agreement_plan_synced_notice(excerpt, summary)
    _emit_plan_pipeline_proposal(
        folder,
        excerpt=excerpt,
        summary=summary,
        notice=notice,
        permissions=permissions,
        on_event=on_event,
        trigger="verified_loop_done",
    )
    return plan_md


def ensure_consensus_plan_sync(folder: Path) -> bool:
    """Backfill plan → question → build for unreconciled consensus agreements."""
    from agent_lab.consensus_agreements import pending_consensus_agreements
    from agent_lab.run_meta import read_run_meta

    run = read_run_meta(folder)
    pending = pending_consensus_agreements(run.get("consensus_agreements"))
    if not pending:
        return False
    latest = pending[-1]
    excerpt = str(latest.get("excerpt") or "").strip()
    if not excerpt:
        return False
    result = maybe_auto_scribe_after_consensus(
        folder,
        consensus_meta={"status": "reached", "anchor": {"excerpt": excerpt}},
        synthesize=False,
        cancelled=False,
        on_event=None,
        permissions=None,
    )
    return result is not None


def ensure_verified_plan_sync(folder: Path) -> bool:
    """Backfill plan → question → build after Oracle VERIFIED (idempotent)."""
    from agent_lab.run_meta import read_run_meta

    run = read_run_meta(folder)
    loop = dict(run.get("verified_loop") or {})
    if str(loop.get("status") or "") != "done":
        return False
    sync = dict(run.get("verified_plan_sync") or {})
    if sync.get("verified_at") == loop.get("verified_at"):
        return False
    result = maybe_auto_scribe_after_verified_loop(
        folder,
        verified_result={"verified_loop": loop},
        cancelled=False,
        on_event=None,
        permissions=None,
    )
    return result is not None


def ensure_session_plan_pipeline(folder: Path) -> bool:
    """Run pending consensus or verified plan auto-sync (best-effort)."""
    changed = ensure_consensus_plan_sync(folder)
    if ensure_verified_plan_sync(folder):
        changed = True
    return changed


def _try_dispatch_turn(
    *,
    body: str,
    topic: str,
    messages: list[ChatMessage],
    run_meta: dict[str, Any],
    folder: Path,
    permissions: dict | None,
    on_event: OnAgentEvent | None,
    clarifier_questions: list[str] | None,
    human_turn_num: int,
) -> list[ChatMessage] | None:
    from agent_lab.room_dispatch import try_dispatch_turn

    replies = try_dispatch_turn(
        body=body,
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        folder=folder,
        permissions=permissions,
        on_event=on_event,
        clarifier_questions=clarifier_questions,
        human_turn=human_turn_num,
    )
    return replies  # type: ignore[return-value]


def _try_delegate_turn(
    *,
    body: str,
    topic: str,
    messages: list[ChatMessage],
    run_meta: dict[str, Any],
    folder: Path,
    permissions: dict | None,
    on_event: OnAgentEvent | None,
    clarifier_questions: list[str] | None,
    human_turn_num: int,
) -> list[ChatMessage] | None:
    return _try_dispatch_turn(
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


def _delegate_run_meta_patch(run_meta: dict[str, Any]) -> dict[str, Any] | None:
    from agent_lab.room_dispatch import dispatch_run_meta_patch

    return dispatch_run_meta_patch(run_meta)


def _communicate_meta_for_turn(
    replies: list[ChatMessage],
    context_log: list[dict[str, Any]] | None,
    *,
    parallel_rounds: int,
    review_mode: bool,
    consensus_mode: bool,
    turn_profile: str | None,
    efficiency_mode: bool,
) -> dict[str, Any]:
    from agent_lab.reply_policy import resolve_reply_policy, summarize_turn_communicate_meta

    policy = resolve_reply_policy(
        parallel_round=parallel_rounds,
        review_mode=review_mode,
        consensus_mode=consensus_mode,
        turn_profile=turn_profile or "",
        efficiency_mode=efficiency_mode,
    )
    return summarize_turn_communicate_meta(replies, context_log, policy=policy)


def _goal_auto_continue_message(result: dict[str, Any] | None) -> str | None:
    if not result or (result.get("check") or {}).get("verdict") != "fail":
        return None
    loop = result.get("goal_loop") or {}
    if len(loop.get("checks") or []) >= int(loop.get("max_checks") or 0):
        return None
    return str(loop.get("continue_prompt") or "").strip() or None


def _verified_loop_continue_message(result: dict[str, Any] | None) -> str | None:
    if not result or not result.get("handled"):
        return None
    loop = result.get("verified_loop") or {}
    if loop.get("status") in {"done", "failed", "cancelled", "pending_approval"}:
        return None
    if result.get("circuit_breaker"):
        return None
    return str(result.get("continue_prompt") or "").strip() or None


def _verified_loop_complete_payload(result: dict[str, Any] | None) -> dict[str, Any]:
    if not result:
        return {}
    loop = result.get("verified_loop") or {}
    return {
        "verified_loop": loop,
        "verified_loop_pending": bool(result.get("verified_loop_pending")),
        "verified_loop_status": loop.get("status"),
        "verified_loop_circuit_breaker": bool(result.get("circuit_breaker")),
    }


def _maybe_verified_loop_after_turn(
    folder: Path,
    messages: list[ChatMessage],
    turn_profile: str | None,
    *,
    cancelled: bool = False,
) -> dict[str, Any] | None:
    from agent_lab.verified_loop import maybe_handle_verified_loop_after_turn

    return maybe_handle_verified_loop_after_turn(
        folder,
        messages,
        turn_profile,
        cancelled=cancelled,
    )
