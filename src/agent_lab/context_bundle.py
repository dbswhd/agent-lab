"""Assembled room agent context (layers + metadata) for all backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from agent_lab.agents.registry import label
from agent_lab.room_context import (
    AGENT_CONNECT_HINT,
    CLAUDE_TOOL_RULES,
    CONVERSATION_GUIDANCE,
    EFFICIENCY_RESPONSE_GUIDANCE,
    _MessageLike,
    build_constraints_block,
    build_turn_bridge_block,
    format_peer_block,
    build_plan_open_block,
    build_recent_turns_block,
    collect_peer_messages,
    dedupe_peer_from_recent,
    extract_agreed_bullets,
    extract_human_gates,
    extract_open_bullets,
    extract_status_tags,
    plan_stale_banner,
    pinned_current_turn_messages,
    prepare_recent_messages,
)
from agent_lab.workspace_roots import workspace_roots_block
from agent_lab.room_turn_state import render_turn_state_block


@dataclass
class ContextBundleMeta:
    agent: str
    parallel_round: int
    review_mode: bool
    turns_omitted: int = 0
    chars_omitted: int = 0
    peer_message_count: int = 0
    peer_deduped: int = 0
    pinned_message_count: int = 0
    layer_chars: dict[str, int] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)
    budget_pct: float = 0.0
    trim_level: str = "ok"
    messages_in_payload: int = 0
    messages_in_turn: int = 0
    messages_in_session: int = 0
    numbered_context: bool = False
    line_range: str = ""
    efficiency_mode: bool = False
    slim_context: bool = False
    pin_capped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "parallel_round": self.parallel_round,
            "review_mode": self.review_mode,
            "turns_omitted": self.turns_omitted,
            "chars_omitted": self.chars_omitted,
            "peer_message_count": self.peer_message_count,
            "peer_deduped": self.peer_deduped,
            "pinned_message_count": self.pinned_message_count,
            "layer_chars": dict(self.layer_chars),
            "limits": dict(self.limits),
            "budget_pct": self.budget_pct,
            "trim_level": self.trim_level,
            "messages_in_payload": self.messages_in_payload,
            "messages_in_turn": self.messages_in_turn,
            "messages_in_session": self.messages_in_session,
            "numbered_context": self.numbered_context,
            "line_range": self.line_range,
            "efficiency_mode": self.efficiency_mode,
            "slim_context": self.slim_context,
            "pin_capped": self.pin_capped,
        }


@dataclass
class ContextBundle:
    constraints: str
    plan_open: str
    bridge: str
    recent: str
    peer: str
    guidance_block: str
    connect_hint: str
    claude_tools: str = ""
    follow_up: str = ""
    turn_state: str = ""
    meta: ContextBundleMeta = field(default_factory=lambda: ContextBundleMeta("", 1))

    def render(self) -> str:
        parts = [self.constraints, self.plan_open]
        if self.turn_state.strip():
            parts.append(self.turn_state)
        if self.bridge.strip():
            parts.append(self.bridge)
        parts.extend([self.recent])
        if self.peer.strip():
            parts.append(self.peer)
        parts.append(self.guidance_block)
        if self.connect_hint.strip():
            parts.append(self.connect_hint)
        block = "\n\n".join(p for p in parts if p)
        if self.claude_tools.strip():
            block = f"{block}\n\n---\n{self.claude_tools.strip()}"
        if self.follow_up.strip():
            block = f"{block}\n{self.follow_up.strip()}"
        return block


def build_slim_consensus_bundle(
    topic: str,
    messages: list[_MessageLike],
    agent: str,
    *,
    permission_lines: str = "",
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
    permissions: dict[str, Any] | None = None,
) -> ContextBundle:
    """Minimal payload for 자유 토론 consensus follow-up (anchor + gates only)."""
    from agent_lab.context_limits import agent_context_limits, efficiency_limits
    from agent_lab.context_meta import enrich_bundle_meta
    from agent_lab.room_context import count_messages, current_turn_message_count

    limits = agent_context_limits()
    eff = efficiency_limits()
    last_user: _MessageLike | None = None
    for m in reversed(messages):
        if m.role == "user":
            last_user = m
            break
    human_text = (last_user.content if last_user else topic).strip()
    if len(human_text) > 1200:
        human_text = human_text[:1199] + "…"
    recent_block = (
        "[이번 Human 질문 · 요약만]\n"
        f"{human_text}\n\n"
        "[이전 턴 대화는 생략 — follow_up의 앵커 제안과 constraints만 따르세요.]"
    )
    agreed = extract_agreed_bullets(plan_md)[: eff.max_agreed_items]
    open_bullets = extract_open_bullets(plan_md)[: eff.max_open_items]
    constraints = build_constraints_block(
        permission_lines=permission_lines,
        human_gates=extract_human_gates(messages, topic),
        agreed_bullets=agreed,
        status_tags=extract_status_tags(messages)[
            : limits.max_status_tags
        ],
        workspace_lines=workspace_roots_block(permissions),
    )
    plan_open = build_plan_open_block(
        open_bullets=open_bullets,
        stale_line=plan_stale_banner(run_meta),
    )
    turn_state_block = render_turn_state_block(
        (run_meta or {}).get("turn_state")
    )
    guidance_block = (
        "---\n"
        f"{CONVERSATION_GUIDANCE}\n"
        f"{EFFICIENCY_RESPONSE_GUIDANCE}\n"
        "---\n"
        f"Respond as {label(agent)} only."
    )
    connect_hint = AGENT_CONNECT_HINT.get(agent, "").strip()
    claude_tools = CLAUDE_TOOL_RULES if agent == "claude" else ""
    meta = ContextBundleMeta(
        agent=agent,
        parallel_round=2,
        review_mode=False,
        efficiency_mode=True,
        slim_context=True,
        pin_capped=True,
    )
    bundle = ContextBundle(
        constraints=constraints,
        plan_open=plan_open,
        bridge="",
        recent=recent_block,
        peer="",
        guidance_block=guidance_block,
        connect_hint=connect_hint,
        claude_tools=claude_tools,
        follow_up="",
        turn_state=turn_state_block,
        meta=meta,
    )
    meta.layer_chars = {
        "constraints": len(constraints),
        "plan_open": len(plan_open),
        "turn_state": len(turn_state_block),
        "bridge": 0,
        "recent": len(recent_block),
        "peer": 0,
        "guidance": len(guidance_block),
        "connect_hint": len(connect_hint),
        "claude_tools": len(claude_tools),
        "follow_up": 0,
        "total": len(bundle.render()),
    }
    meta.line_range = ""
    enrich_bundle_meta(
        meta,
        bundle,
        messages_in_payload=1 if last_user else 0,
        messages_in_turn=current_turn_message_count(messages),
        messages_in_session=count_messages(messages),
    )
    return bundle


def build_context_bundle(
    topic: str,
    messages: list[_MessageLike],
    agent: str,
    *,
    permission_lines: str = "",
    parallel_round: int = 1,
    review_mode: bool = False,
    review_advocate: str | None = None,
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
    permissions: dict[str, Any] | None = None,
    format_thread: Callable[[str, list[_MessageLike]], str] | None = None,
    all_messages: list[_MessageLike] | None = None,
    efficiency_mode: bool = False,
    slim_context: bool = False,
) -> ContextBundle:
    """Build layered context for one agent call (discuss / plan agent rounds)."""
    if slim_context and efficiency_mode:
        return build_slim_consensus_bundle(
            topic,
            messages,
            agent,
            permission_lines=permission_lines,
            plan_md=plan_md,
            run_meta=run_meta,
            permissions=permissions,
        )

    from agent_lab.context_limits import agent_context_limits, efficiency_limits
    from agent_lab.context_meta import enrich_bundle_meta
    from agent_lab.room_context import (
        agent_thread_formatter,
        count_messages,
        current_turn_message_count,
    )

    full = all_messages if all_messages is not None else messages
    limits = agent_context_limits()
    thread_fmt = format_thread or agent_thread_formatter(full, numbered=limits.numbered_context)

    eff = efficiency_limits() if efficiency_mode else None
    pin_before = len(pinned_current_turn_messages(messages)) if efficiency_mode else 0
    trimmed, turns_omitted, chars_omitted, pinned_count = prepare_recent_messages(
        messages, efficiency_mode=efficiency_mode
    )
    pin_capped = efficiency_mode and pinned_count < pin_before

    peer_msgs = collect_peer_messages(messages, agent, parallel_round)
    recent_msgs, peer_deduped = dedupe_peer_from_recent(trimmed, peer_msgs)

    agreed = extract_agreed_bullets(plan_md)
    open_bullets = extract_open_bullets(plan_md)
    if eff:
        agreed = agreed[: eff.max_agreed_items]
        open_bullets = open_bullets[: eff.max_open_items]
    constraints = build_constraints_block(
        permission_lines=permission_lines,
        human_gates=extract_human_gates(messages, topic),
        agreed_bullets=agreed,
        status_tags=extract_status_tags(trimmed),
        workspace_lines=workspace_roots_block(permissions),
    )
    plan_open = build_plan_open_block(
        open_bullets=open_bullets,
        stale_line=plan_stale_banner(run_meta),
    )
    turn_state_block = render_turn_state_block(
        (run_meta or {}).get("turn_state")
    )
    bridge_block = build_turn_bridge_block(
        messages, parallel_round=parallel_round
    )
    recent_block, line_range = build_recent_turns_block(
        topic=topic,
        messages=recent_msgs,
        format_thread=thread_fmt,
        all_messages=full,
        turns_omitted=turns_omitted,
        chars_omitted=chars_omitted,
        peer_deduped=peer_deduped,
        numbered=limits.numbered_context,
    )
    peer_block = format_peer_block(peer_msgs)

    connect_hint = AGENT_CONNECT_HINT.get(agent, "").strip()
    guidance_parts = [CONVERSATION_GUIDANCE]
    if efficiency_mode:
        guidance_parts.append(EFFICIENCY_RESPONSE_GUIDANCE)
    guidance_block = (
        "---\n"
        + "\n".join(guidance_parts)
        + "\n---\n"
        f"Respond as {label(agent)} only."
    )

    follow_up = ""
    if peer_block:
        follow_up = (
            "같은 Human 턴 안에서 동료가 이미 말했습니다. "
            "[이번 턴 · 동료 발화]를 기준으로 이어서 답하고, 겹치는 내용은 짧게 넘기세요."
        )
        if review_mode and parallel_round >= 2 and review_advocate:
            if agent == review_advocate:
                follow_up += (
                    "\n[쟁점 검토 — 반박] "
                    "1라운드 주장 중 가장 약한 가정 하나를 골라 반박하세요."
                )
            else:
                follow_up += (
                    f"\n[쟁점 검토 — 검토] "
                    f"{label(review_advocate)}의 반박에 답하세요(인정 또는 반론)."
                )
        elif parallel_round >= 2:
            follow_up += "\n2라운드(순차): 1라운드 동료 발화에 이어서 답하세요."

    claude_tools = CLAUDE_TOOL_RULES if agent == "claude" else ""

    meta = ContextBundleMeta(
        agent=agent,
        parallel_round=parallel_round,
        review_mode=review_mode,
        turns_omitted=turns_omitted,
        chars_omitted=chars_omitted,
        peer_message_count=len(peer_msgs),
        peer_deduped=peer_deduped,
        pinned_message_count=pinned_count,
        efficiency_mode=efficiency_mode,
        slim_context=False,
        pin_capped=pin_capped,
    )
    bundle = ContextBundle(
        constraints=constraints,
        plan_open=plan_open,
        bridge=bridge_block,
        recent=recent_block,
        peer=peer_block,
        guidance_block=guidance_block,
        connect_hint=connect_hint,
        claude_tools=claude_tools,
        follow_up=follow_up,
        turn_state=turn_state_block,
        meta=meta,
    )
    meta.layer_chars = {
        "constraints": len(constraints),
        "plan_open": len(plan_open),
        "turn_state": len(turn_state_block),
        "bridge": len(bridge_block),
        "recent": len(recent_block),
        "peer": len(peer_block),
        "guidance": len(guidance_block),
        "connect_hint": len(connect_hint),
        "claude_tools": len(claude_tools),
        "follow_up": len(follow_up),
        "total": len(bundle.render()),
    }
    meta.line_range = line_range
    enrich_bundle_meta(
        meta,
        bundle,
        messages_in_payload=len(recent_msgs),
        messages_in_turn=current_turn_message_count(full),
        messages_in_session=count_messages(full),
    )
    return bundle
