"""Turn-flow helpers: checkpoint, budget, divergence emit, stage routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.room.messages import ChatMessage, OnAgentEvent
from agent_lab.room.session_persist import persist_chat_checkpoint


def checkpoint_chat(
    folder: Path | None,
    messages: list[ChatMessage],
    *,
    topic: str,
) -> None:
    if folder is None:
        return
    persist_chat_checkpoint(folder, messages, topic=topic)


def apply_turn_agent_mentions(
    user_text: str,
    active_agents: list[Any],
    run_meta: dict[str, Any],
    *,
    roster_pool: list[Any] | None = None,
) -> tuple[str, list[Any], list[str], str | None]:
    """When Human @-targets agents, shrink roster and strip tokens from user text."""
    from agent_lab.room.agent_mentions import (
        apply_agent_mention_filter,
        mention_not_in_roster_message,
        out_of_roster_mentions,
    )

    pool = roster_pool if roster_pool is not None else active_agents
    pool_list = [str(a) for a in pool]
    oor = out_of_roster_mentions(user_text, pool_list)
    if oor:
        run_meta.pop("_turn_target_agents", None)
        return user_text, active_agents, [], mention_not_in_roster_message(oor, pool_list)
    filtered, stripped, targets = apply_agent_mention_filter(
        user_text,
        [str(a) for a in active_agents],
        roster_pool=pool_list,
    )
    if not targets:
        run_meta.pop("_turn_target_agents", None)
        return user_text, active_agents, [], None
    run_meta["_turn_target_agents"] = targets
    run_meta["agents"] = [str(a) for a in filtered]
    return stripped, filtered, targets, None


def emit_mention_roster_error(on_event: OnAgentEvent | None, message: str) -> None:
    """Fail the turn immediately when @-targets are outside the session roster."""
    if not on_event:
        return
    payload = {
        "status": "failed",
        "reason": "mention_not_in_roster",
        "message": message,
        "agent_reply_count": 0,
        "failed_agents": [],
        "succeeded_agents": [],
    }
    on_event("turn_failed", payload)
    on_event("run_failed", {"message": message})


def direct_turn_for_mention_targets(targets: list[str]) -> bool:
    """Single explicit @-mention → one agent, one round (skip consensus loop)."""
    return len(targets) == 1


def emit_divergence_options(
    run_meta: dict[str, Any] | None,
    replies: list[ChatMessage],
    on_event: OnAgentEvent | None,
    cancelled: bool,
) -> None:
    """Emit divergence options for human selection; never triggers execute."""
    from agent_lab.divergence import format_divergence_options, is_divergence_profile

    profile = str((run_meta or {}).get("turn_profile") or "")
    if cancelled or not on_event or not replies or not is_divergence_profile(profile):
        return
    options = format_divergence_options(replies)
    if options:
        on_event("divergence_options", {"options": options, "count": len(options)})


def session_hard_cap_enabled() -> bool:
    import os

    return (os.getenv("AGENT_LAB_SESSION_HARD_CAP") or "").strip().lower() in ("1", "true", "yes", "on")


def emit_budget_status(run_meta: dict[str, Any] | None, on_event: OnAgentEvent | None) -> None:
    """Surface cumulative session cost; enable adaptive efficiency on first over-transition."""
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
    _maybe_enable_adaptive_efficiency(run_meta, on_event, action)


def _maybe_enable_adaptive_efficiency(
    run_meta: dict[str, Any],
    on_event: OnAgentEvent,
    action: dict[str, Any],
) -> None:
    if run_meta.get("adaptive_efficiency"):
        return
    reason: str | None = None
    if action.get("over"):
        reason = "session_budget_over"
    elif action.get("warn"):
        reason = "session_budget_warn"
    else:
        token_budget = run_meta.get("token_budget")
        if isinstance(token_budget, dict) and token_budget.get("critical"):
            reason = "context_budget_critical"
    if reason is None:
        from agent_lab.room.messages import _human_turn_count

        messages = run_meta.get("_checkpoint_messages")
        human_turn = _human_turn_count(messages) if isinstance(messages, list) else 0
        if human_turn <= 0:
            human_turn = int(run_meta.get("human_turn") or 0)
        if human_turn >= 5:
            reason = "human_turn_threshold"
    if reason is None:
        return
    run_meta["adaptive_efficiency"] = True
    on_event(
        "efficiency_auto_enabled",
        {
            "reason": reason,
            "cumulative": action.get("cumulative"),
            "usd_limit": action.get("usd_limit"),
            "token_limit": action.get("token_limit"),
        },
    )
    if action.get("over") and session_hard_cap_enabled() and not run_meta.get("budget_exhausted"):
        run_meta["budget_exhausted"] = True
        on_event("budget_exhausted", {"cumulative": action.get("cumulative")})


def ensure_adaptive_efficiency_for_turn(
    run_meta: dict[str, Any] | None,
    *,
    human_turn: int,
) -> None:
    """Proactive efficiency when context budget is critical or session is long."""
    if not isinstance(run_meta, dict) or run_meta.get("adaptive_efficiency"):
        return
    token_budget = run_meta.get("token_budget")
    if isinstance(token_budget, dict) and token_budget.get("critical"):
        run_meta["adaptive_efficiency"] = True
        return
    if human_turn >= 5:
        run_meta["adaptive_efficiency"] = True


def resolve_stage_routing(
    run_meta: dict[str, Any],
    *,
    turn_profile: str | None,
    consensus_mode: bool,
    folder: Path | None,
) -> bool:
    """Phase-aware single-vs-panel routing (no-op unless AGENT_LAB_STAGE_ROUTING is on)."""
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


def after_agent_replies_checkpoint(
    folder: Path | None,
    messages: list[ChatMessage],
    *,
    topic: str,
    run_meta: dict[str, Any] | None,
    replies: list[ChatMessage],
    on_event: OnAgentEvent | None,
    cancelled: bool,
) -> None:
    checkpoint_chat(folder, messages, topic=topic)
    emit_divergence_options(run_meta, replies, on_event, cancelled)
    emit_budget_status(run_meta, on_event)


# Backward-compatible aliases (tests import via turn_flow)
_checkpoint_chat = checkpoint_chat
_emit_divergence_options = emit_divergence_options
_session_hard_cap_enabled = session_hard_cap_enabled
_emit_budget_status = emit_budget_status
_resolve_stage_routing = resolve_stage_routing
