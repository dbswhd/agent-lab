"""Assembled room agent context (layers + metadata) for all backends."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from agent_lab.agent_thread_resume import build_agent_thread_resume_block
from agent_lab.room_context import (
    AGENT_CONNECT_HINT,
    agent_tool_rules,
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
from agent_lab.room_agent_capabilities import (
    agent_capability_cwd,
    agent_workspace_lines,
    capability_preamble_block,
)
from agent_lab.room_objections import build_challenge_owner_block, build_objection_block
from agent_lab.room_turn_state import render_turn_state_block
from agent_lab.room_artifacts import build_artifacts_block
from agent_lab.room_mailbox import build_mailbox_block
from agent_lab.room_tasks import build_team_task_block
from agent_lab.session_guidance import (
    build_session_guidance_block,
    sync_session_meta,
)
from agent_lab.plugin_discovery import build_plugin_allowlist_block
from agent_lab.reply_policy import (
    build_guidance_parts,
    envelope_follow_up_block,
    resolve_reply_policy,
)
from agent_lab.gate_snapshot import compute_gate_snapshot, format_gate_snapshot_block

ARTIFACT_ONLY_RECENT_MAX_CHARS = 1200


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
    capability_cwd: str = ""
    context_mode: str = "full"
    recent_max_chars: int | None = None
    peer_suppressed: bool = False

    def to_dict(self) -> dict[str, Any]:
        row = {
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
            "context_mode": self.context_mode,
        }
        if self.capability_cwd:
            row["capability_cwd"] = self.capability_cwd
        if self.recent_max_chars is not None:
            row["recent_max_chars"] = self.recent_max_chars
        if self.peer_suppressed:
            row["peer_suppressed"] = True
        return row


def _workspace_lines_for_agent(
    agent: str,
    permissions: dict[str, Any] | None,
    run_meta: dict[str, Any] | None,
) -> str:
    if run_meta and isinstance(run_meta.get("agent_capabilities"), dict):
        return agent_workspace_lines(agent, permissions, run_meta)
    return workspace_roots_block(permissions)


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


def _latest_human_text(topic: str, messages: list[_MessageLike]) -> tuple[str, bool]:
    last_user: _MessageLike | None = None
    for m in reversed(messages):
        if m.role == "user":
            last_user = m
            break
    human_text = (last_user.content if last_user else topic).strip()
    if len(human_text) > ARTIFACT_ONLY_RECENT_MAX_CHARS:
        human_text = human_text[: ARTIFACT_ONLY_RECENT_MAX_CHARS - 1] + "…"
    return human_text, last_user is not None


def _build_human_only_recent_block(
    topic: str,
    messages: list[_MessageLike],
) -> tuple[str, bool]:
    human_text, has_user = _latest_human_text(topic, messages)
    return (
        "[이번 Human 질문 · 요약만]\n"
        f"{human_text}\n\n"
        "[이전 턴 대화는 생략 — follow_up의 앵커 제안과 constraints만 따르세요.]",
        has_user,
    )


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _artifact_only_context(
    run_meta: dict[str, Any] | None,
    agent: str,
    parallel_round: int,
) -> bool:
    if not _env_bool("AGENT_LAB_F2_ARTIFACT_ONLY", True):
        return False
    if str(agent).strip().lower() != "cursor" or parallel_round < 2:
        return False
    profile = str((run_meta or {}).get("turn_profile") or "").strip().lower()
    return profile == "specialist" or bool((run_meta or {}).get("research_mode"))


def build_slim_consensus_bundle(
    topic: str,
    messages: list[_MessageLike],
    agent: str,
    *,
    permission_lines: str = "",
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
    permissions: dict[str, Any] | None = None,
    consensus_mode: bool = True,
    efficiency_mode: bool = True,
) -> ContextBundle:
    """Minimal payload for 자유 토론 consensus follow-up (anchor + gates only)."""
    from agent_lab.context_limits import agent_context_limits, efficiency_limits
    from agent_lab.context_meta import enrich_bundle_meta
    from agent_lab.agents.registry import label
    from agent_lab.room_context import count_messages, current_turn_message_count

    limits = agent_context_limits()
    eff = efficiency_limits()
    recent_block, has_user = _build_human_only_recent_block(topic, messages)
    agreed = extract_agreed_bullets(plan_md)[: eff.max_agreed_items]
    open_bullets = extract_open_bullets(plan_md)[: eff.max_open_items]
    if run_meta is not None:
        sync_session_meta(
            run_meta,
            topic=topic,
            messages=messages,
            plan_md=plan_md,
            permissions=permissions,
        )
    session_guidance = build_session_guidance_block(run_meta, plan_md=plan_md)
    constraints = build_constraints_block(
        permission_lines=permission_lines,
        human_gates=extract_human_gates(messages, topic),
        agreed_bullets=agreed,
        status_tags=extract_status_tags(messages)[
            : limits.max_status_tags
        ],
        workspace_lines=_workspace_lines_for_agent(agent, permissions, run_meta),
    )
    if session_guidance.strip():
        constraints = f"{constraints}\n\n{session_guidance.strip()}"
    constraints = _append_mission_track_c_blocks(
        constraints, run_meta=run_meta, plan_md=plan_md
    )
    resume_block = build_agent_thread_resume_block(agent, run_meta)
    if resume_block.strip():
        constraints = f"{constraints}\n\n{resume_block.strip()}"
    plugin_block = build_plugin_allowlist_block(agent, run_meta)
    if plugin_block.strip():
        constraints = f"{constraints}\n\n{plugin_block.strip()}"
    cap_block = capability_preamble_block(agent, run_meta, parallel_round=2)
    if cap_block.strip():
        constraints = f"{constraints}\n\n{cap_block.strip()}"
    team_block = build_team_task_block(run_meta, agent)
    if team_block.strip():
        constraints = f"{constraints}\n\n{team_block.strip()}"
    mailbox_block = build_mailbox_block(run_meta, agent)
    if mailbox_block.strip():
        constraints = f"{constraints}\n\n{mailbox_block.strip()}"
    artifacts_block = build_artifacts_block(
        run_meta, agent, parallel_round=2
    )
    if artifacts_block.strip():
        constraints = f"{constraints}\n\n{artifacts_block.strip()}"
    objection_block = build_objection_block(run_meta, agent)
    if objection_block.strip():
        constraints = f"{constraints}\n\n{objection_block.strip()}"
    challenge_block = build_challenge_owner_block(run_meta, agent)
    if challenge_block.strip():
        constraints = f"{constraints}\n\n{challenge_block.strip()}"
    gate_block = format_gate_snapshot_block(compute_gate_snapshot(run_meta))
    if gate_block.strip():
        constraints = f"{constraints}\n\n{gate_block.strip()}"
    plan_open = build_plan_open_block(
        open_bullets=open_bullets,
        stale_line=plan_stale_banner(run_meta),
    )
    turn_state_block = render_turn_state_block(
        (run_meta or {}).get("turn_state")
    )
    reply_policy = resolve_reply_policy(
        parallel_round=2,
        consensus_mode=consensus_mode,
        turn_profile=str((run_meta or {}).get("turn_profile") or ""),
        efficiency_mode=efficiency_mode,
    )
    guidance_parts = build_guidance_parts(reply_policy)
    guidance_block = (
        "---\n"
        + "\n".join(guidance_parts)
        + "\n---\n"
        f"Respond as {label(agent)} only."
    )
    follow_up = envelope_follow_up_block(reply_policy, context="consensus")
    connect_hint = AGENT_CONNECT_HINT.get(agent, "").strip()
    tool_rules = agent_tool_rules(agent)
    meta = ContextBundleMeta(
        agent=agent,
        parallel_round=2,
        review_mode=False,
        efficiency_mode=True,
        slim_context=True,
        pin_capped=True,
        capability_cwd=agent_capability_cwd(agent, permissions, run_meta),
    )
    bundle = ContextBundle(
        constraints=constraints,
        plan_open=plan_open,
        bridge="",
        recent=recent_block,
        peer="",
        guidance_block=guidance_block,
        connect_hint=connect_hint,
        claude_tools=tool_rules,
        follow_up=follow_up,
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
        "claude_tools": len(tool_rules),
        "follow_up": len(follow_up),
        "total": len(bundle.render()),
    }
    meta.line_range = ""
    enrich_bundle_meta(
        meta,
        bundle,
        messages_in_payload=1 if has_user else 0,
        messages_in_turn=current_turn_message_count(messages),
        messages_in_session=count_messages(messages),
    )
    return bundle


def _append_mission_track_c_blocks(
    constraints: str,
    *,
    run_meta: dict[str, Any] | None,
    plan_md: str,
) -> str:
    from agent_lab.mission_loop import build_mission_wisdom_block
    from agent_lab.repo_tree_context import (
        build_per_dir_agents_block,
        build_repo_tree_block,
    )
    from agent_lab.workspace_md import PER_DIR_AGENTS_GUIDANCE_HEADER

    out = constraints
    mission_wisdom = build_mission_wisdom_block(run_meta)
    if mission_wisdom.strip():
        out = f"{out}\n\n{mission_wisdom.strip()}"
    repo_block = build_repo_tree_block(run_meta)
    if repo_block.strip():
        out = f"{out}\n\n{repo_block.strip()}"
    if PER_DIR_AGENTS_GUIDANCE_HEADER not in out:
        per_dir = build_per_dir_agents_block(run_meta, plan_md)
        if per_dir.strip():
            out = f"{out}\n\n{per_dir.strip()}"
    return out


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
    consensus_mode: bool = False,
) -> ContextBundle:
    """Build layered context for one agent call (discuss / plan agent rounds)."""
    from agent_lab.context_layers import should_use_mission_slim_bundle

    if should_use_mission_slim_bundle(run_meta) and not (
        slim_context and efficiency_mode
    ):
        slim_context = True
        efficiency_mode = True
    if slim_context and efficiency_mode:
        return build_slim_consensus_bundle(
            topic,
            messages,
            agent,
            permission_lines=permission_lines,
            plan_md=plan_md,
            run_meta=run_meta,
            permissions=permissions,
            consensus_mode=consensus_mode,
            efficiency_mode=efficiency_mode,
        )

    from agent_lab.context_limits import agent_context_limits, efficiency_limits
    from agent_lab.context_meta import enrich_bundle_meta
    from agent_lab.agents.registry import label
    from agent_lab.room_context import (
        agent_thread_formatter,
        count_messages,
        current_turn_message_count,
    )

    full = all_messages if all_messages is not None else messages
    limits = agent_context_limits()
    thread_fmt = format_thread or agent_thread_formatter(
        full,
        numbered=limits.numbered_context,
    )
    artifact_only = _artifact_only_context(run_meta, agent, parallel_round)

    eff = efficiency_limits() if efficiency_mode else None
    pin_before = len(pinned_current_turn_messages(messages)) if efficiency_mode else 0
    trimmed, turns_omitted, chars_omitted, pinned_count = prepare_recent_messages(
        messages, efficiency_mode=efficiency_mode
    )
    pin_capped = efficiency_mode and pinned_count < pin_before

    peer_msgs = collect_peer_messages(messages, agent, parallel_round)
    if artifact_only:
        recent_msgs, peer_deduped = [], 0
    else:
        recent_msgs, peer_deduped = dedupe_peer_from_recent(trimmed, peer_msgs)

    agreed = extract_agreed_bullets(plan_md)
    open_bullets = extract_open_bullets(plan_md)
    if eff:
        agreed = agreed[: eff.max_agreed_items]
        open_bullets = open_bullets[: eff.max_open_items]
    if run_meta is not None:
        sync_session_meta(
            run_meta,
            topic=topic,
            messages=full,
            plan_md=plan_md,
            permissions=permissions,
        )
    session_guidance = build_session_guidance_block(run_meta, plan_md=plan_md)
    constraints = build_constraints_block(
        permission_lines=permission_lines,
        human_gates=extract_human_gates(messages, topic),
        agreed_bullets=agreed,
        status_tags=extract_status_tags(trimmed),
        workspace_lines=_workspace_lines_for_agent(agent, permissions, run_meta),
    )
    if session_guidance.strip():
        constraints = f"{constraints}\n\n{session_guidance.strip()}"
    constraints = _append_mission_track_c_blocks(
        constraints, run_meta=run_meta, plan_md=plan_md
    )
    resume_block = build_agent_thread_resume_block(agent, run_meta)
    if resume_block.strip():
        constraints = f"{constraints}\n\n{resume_block.strip()}"
    plugin_block = build_plugin_allowlist_block(agent, run_meta)
    if plugin_block.strip():
        constraints = f"{constraints}\n\n{plugin_block.strip()}"
    cap_block = capability_preamble_block(
        agent, run_meta, parallel_round=parallel_round
    )
    if cap_block.strip():
        constraints = f"{constraints}\n\n{cap_block.strip()}"
    team_block = build_team_task_block(run_meta, agent)
    if team_block.strip():
        constraints = f"{constraints}\n\n{team_block.strip()}"
    mailbox_block = build_mailbox_block(run_meta, agent)
    if mailbox_block.strip():
        constraints = f"{constraints}\n\n{mailbox_block.strip()}"
    artifacts_block = build_artifacts_block(
        run_meta,
        agent,
        parallel_round=parallel_round,
        artifact_only=artifact_only,
    )
    if artifacts_block.strip():
        constraints = f"{constraints}\n\n{artifacts_block.strip()}"
    objection_block = build_objection_block(run_meta, agent)
    if objection_block.strip():
        constraints = f"{constraints}\n\n{objection_block.strip()}"
    challenge_block = build_challenge_owner_block(run_meta, agent)
    if challenge_block.strip():
        constraints = f"{constraints}\n\n{challenge_block.strip()}"
    gate_block = format_gate_snapshot_block(compute_gate_snapshot(run_meta))
    if gate_block.strip():
        constraints = f"{constraints}\n\n{gate_block.strip()}"
    plan_open = build_plan_open_block(
        open_bullets=open_bullets,
        stale_line=plan_stale_banner(run_meta),
    )
    turn_state_block = (
        ""
        if artifact_only
        else render_turn_state_block((run_meta or {}).get("turn_state"))
    )
    if artifact_only:
        bridge_block = ""
        recent_block, has_user_in_recent = _build_human_only_recent_block(
            topic, messages
        )
        line_range = ""
        peer_block = ""
    else:
        has_user_in_recent = any(m.role == "user" for m in recent_msgs)
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
    profile = str((run_meta or {}).get("turn_profile") or "").strip().lower()
    reply_policy = resolve_reply_policy(
        parallel_round=parallel_round,
        review_mode=review_mode,
        consensus_mode=consensus_mode,
        turn_profile=profile,
        efficiency_mode=efficiency_mode,
    )
    guidance_parts = build_guidance_parts(reply_policy)
    if profile == "analyze":
        guidance_parts.insert(
            0,
            "[Analyze turn] Observe and report risks only. "
            "Do not use PROPOSE/ENDORSE/BLOCK envelope acts.",
        )
    guidance_block = (
        "---\n"
        + "\n".join(guidance_parts)
        + "\n---\n"
        f"Respond as {label(agent)} only."
    )

    follow_up = ""
    env_ctx = "consensus" if consensus_mode else ("review" if review_mode else "discuss")
    envelope_block = envelope_follow_up_block(reply_policy, context=env_ctx)
    if envelope_block.strip():
        follow_up = envelope_block.strip()
    if artifact_only:
        follow_up = (
            "[artifact-only R2]\n"
            "full chat 없음 — artifacts와 이번 Human 질문만 근거로 답하세요. "
            "R1 동료 발화 본문은 payload에 없으며 artifacts가 R1 산출물을 대체합니다."
        )
    elif peer_block:
        peer_follow = (
            "같은 Human 턴 안에서 동료가 이미 말했습니다. "
            "[이번 턴 · 동료 발화]를 기준으로 이어서 답하고, 겹치는 내용은 짧게 넘기세요."
        )
        follow_up = "\n\n".join(x for x in (follow_up, peer_follow) if x.strip())
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
            follow_up += (
                "\n2라운드(순차 · 토론): 동료 의견을 **이어가거나 보완**하세요. "
                "새 쟁점을 열기보다 합치거나 확장하는 쪽을 우선하세요."
            )

    tool_rules = agent_tool_rules(agent)

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
        capability_cwd=agent_capability_cwd(agent, permissions, run_meta),
        context_mode="artifact_only" if artifact_only else "full",
        recent_max_chars=(
            ARTIFACT_ONLY_RECENT_MAX_CHARS if artifact_only else None
        ),
        peer_suppressed=artifact_only,
    )
    bundle = ContextBundle(
        constraints=constraints,
        plan_open=plan_open,
        bridge=bridge_block,
        recent=recent_block,
        peer=peer_block,
        guidance_block=guidance_block,
        connect_hint=connect_hint,
        claude_tools=tool_rules,
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
        "claude_tools": len(tool_rules),
        "follow_up": len(follow_up),
        "total": len(bundle.render()),
    }
    meta.line_range = line_range
    enrich_bundle_meta(
        meta,
        bundle,
        messages_in_payload=(
            1 if artifact_only and has_user_in_recent else len(recent_msgs)
        ),
        messages_in_turn=current_turn_message_count(full),
        messages_in_session=count_messages(full),
    )
    return bundle
