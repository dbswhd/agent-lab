"""Assembled room agent context (layers + metadata) for all backends."""

from __future__ import annotations

import os
from typing import Any, Callable, cast

from agent_lab.run.state import RunStateLike

from agent_lab.core.context_bundle import ContextBundle, ContextBundleMeta
from agent_lab.agent.thread_resume import build_agent_thread_resume_block
from agent_lab.room.context import (
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
from agent_lab.workspace.roots import workspace_roots_block
from agent_lab.room.agent_capabilities import (
    agent_capability_cwd,
    agent_workspace_lines,
    capability_preamble_block,
)
from agent_lab.room.objections import build_challenge_owner_block, build_objection_block
from agent_lab.room.turn_state import render_turn_state_block
from agent_lab.room.artifacts import build_artifacts_block
from agent_lab.room.mailbox import build_mailbox_block
from agent_lab.room.tasks import build_team_task_block
from agent_lab.session.guidance import (
    build_session_guidance_block,
    sync_session_meta,
)
from agent_lab.plugin_discovery import build_plugin_allowlist_block
from agent_lab.reply_policy import (
    apply_inbox_fork_grace_policy,
    build_guidance_parts,
    envelope_follow_up_block,
    resolve_reply_policy,
)
from agent_lab.runtime.policy import PolicyEngine
from agent_lab.env_flags import env_bool


def _format_clarity_facts(run_meta: RunStateLike | None) -> str:
    """Confirmed CLARIFY facts → constraints injection (deep-interview established_facts analog)."""
    if not isinstance(run_meta, dict):
        return ""
    from agent_lab.clarity import format_facts_block

    return format_facts_block(run_meta)


def _format_decision_ledger(run_meta: RunStateLike | None, *, max_entries: int = 6) -> str:
    """Compact recent goal-ledger decisions for anti-drift re-grounding (run.json goal_ledger)."""
    if not isinstance(run_meta, dict):
        return ""
    raw = run_meta.get("goal_ledger")
    if not isinstance(raw, list) or not raw:
        return ""
    lines: list[str] = []
    for entry in raw[-max_entries:]:
        if not isinstance(entry, dict):
            continue
        event = str(entry.get("event") or "").strip()
        if not event:
            continue
        suffix = " · ".join(
            part for part in (str(entry.get("phase") or "").strip(), str(entry.get("note") or "").strip()) if part
        )
        lines.append(f"- {event}{(' · ' + suffix) if suffix else ''}")
    if not lines:
        return ""
    return "\n".join(["[결정 로그]", *lines])


def _format_grounding_block(run_meta: RunStateLike | None, *, consensus_mode: bool) -> str:
    """Confirmed-state injection for an agent turn.

    Default / solo / AGENT_LAB_ANTIDRIFT off: the plain confirmed-facts block (OFF-parity).
    Anti-drift panel turn (flag on AND consensus_mode): a re-grounding anchor that re-injects the
    confirmed facts plus the recent decision ledger each panel turn so the panel does not drift
    from established conclusions.
    """
    facts = _format_clarity_facts(run_meta)
    from agent_lab.turn_modes import antidrift_enabled

    if not (consensus_mode and antidrift_enabled()):
        return facts
    ledger = _format_decision_ledger(run_meta)
    if not facts and not ledger:
        return ""
    parts = ["[anti-drift · 상태 재정렬 — 아래 확정 사실/결정에서 벗어나지 말 것]"]
    if facts:
        parts.append(facts)
    if ledger:
        parts.append(ledger)
    return "\n\n".join(parts)


ARTIFACT_ONLY_RECENT_MAX_CHARS = 1200


def _workspace_lines_for_agent(
    agent: str,
    permissions: dict[str, Any] | None,
    run_meta: RunStateLike | None,
) -> str:
    if run_meta and isinstance(run_meta.get("agent_capabilities"), dict):
        return agent_workspace_lines(agent, permissions, run_meta)
    return workspace_roots_block(permissions)


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


def _artifact_only_context(
    run_meta: RunStateLike | None,
    agent: str,
    parallel_round: int,
) -> bool:
    if not env_bool("AGENT_LAB_F2_ARTIFACT_ONLY", True):
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
    run_meta: RunStateLike | None = None,
    permissions: dict[str, Any] | None = None,
    consensus_mode: bool = True,
    efficiency_mode: bool = True,
) -> ContextBundle:
    """Minimal payload for 자유 토론 consensus follow-up (anchor + gates only)."""
    from agent_lab.context.limits import agent_context_limits, efficiency_limits
    from agent_lab.context.meta import enrich_bundle_meta
    from agent_lab.agents.registry import AgentId, label
    from agent_lab.room.context import count_messages, current_turn_message_count

    limits = agent_context_limits()
    eff = efficiency_limits()
    recent_block, has_user = _build_human_only_recent_block(topic, messages)
    agreed = extract_agreed_bullets(plan_md)[: eff.max_agreed_items]
    open_bullets = extract_open_bullets(plan_md)[: eff.max_open_items]
    if run_meta is not None:
        sync_session_meta(
            run_meta,
            topic=topic,
            messages=cast(Any, messages),
            plan_md=plan_md,
            permissions=permissions,
        )
    session_guidance = build_session_guidance_block(run_meta, plan_md=plan_md)
    from agent_lab.room.roster_context import active_agents_from_run_meta
    from agent_lab.room.tasks import team_lead as session_team_lead

    active_roster = active_agents_from_run_meta(run_meta)
    constraints = build_constraints_block(
        permission_lines=permission_lines,
        human_gates=extract_human_gates(messages, topic),
        agreed_bullets=agreed,
        status_tags=extract_status_tags(messages)[: limits.max_status_tags],
        workspace_lines=_workspace_lines_for_agent(agent, permissions, run_meta),
        active_agents=active_roster,
        team_lead=session_team_lead(run_meta) if run_meta else None,
    )
    if session_guidance.strip():
        constraints = f"{constraints}\n\n{session_guidance.strip()}"
    grounding_block = _format_grounding_block(run_meta, consensus_mode=consensus_mode)
    if grounding_block.strip():
        constraints = f"{constraints}\n\n{grounding_block.strip()}"
    constraints = _append_mission_track_c_blocks(constraints, run_meta=run_meta, plan_md=plan_md)
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
    artifacts_block = build_artifacts_block(run_meta, agent, parallel_round=2)
    if artifacts_block.strip():
        constraints = f"{constraints}\n\n{artifacts_block.strip()}"
    objection_block = build_objection_block(run_meta, agent)
    if objection_block.strip():
        constraints = f"{constraints}\n\n{objection_block.strip()}"
    challenge_block = build_challenge_owner_block(run_meta, agent)
    if challenge_block.strip():
        constraints = f"{constraints}\n\n{challenge_block.strip()}"
    snap = PolicyEngine.gate_snapshot(run_meta)
    gate_block = PolicyEngine.format_gate_block(snap)
    if gate_block.strip():
        constraints = f"{constraints}\n\n{gate_block.strip()}"
    plan_open = build_plan_open_block(
        open_bullets=open_bullets,
        stale_line=plan_stale_banner(run_meta),
    )
    turn_state_block = render_turn_state_block((run_meta or {}).get("turn_state"))
    reply_policy = apply_inbox_fork_grace_policy(
        resolve_reply_policy(
            parallel_round=2,
            consensus_mode=consensus_mode,
            turn_profile=str((run_meta or {}).get("turn_profile") or ""),
            efficiency_mode=efficiency_mode,
        ),
        run_meta,
    )
    guidance_parts = build_guidance_parts(reply_policy, run_meta=run_meta, agent=agent, active_agents=active_roster)
    from agent_lab.room.dispatch_intents import build_dispatch_intent_block

    dispatch_block = build_dispatch_intent_block(run_meta, agent)
    if dispatch_block.strip():
        guidance_parts.append(dispatch_block.strip())
    guidance_block = "---\n" + "\n".join(guidance_parts) + f"\n---\nRespond as {label(cast(AgentId, agent))} only."
    follow_up = envelope_follow_up_block(reply_policy, context="consensus")
    connect_hint = AGENT_CONNECT_HINT.get(agent, "").strip()
    tool_rules = agent_tool_rules(agent, run_meta, active_agents=active_roster)
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
        "guidance_block": len(guidance_block),
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
    _record_context_bundle_metrics(run_meta, meta, agent=agent, mode="slim")
    # CX8 shadow-parity pass — see the matching block at the end of
    # build_context_bundle for the full rationale. This is the slim path's
    # counterpart: DISCUSS/PLAN_GATE/PLAN_REJECT phases redirect here BEFORE
    # ever reaching build_context_bundle's own tail (should_use_mission_
    # slim_bundle), so without this second splice point, the single most
    # common activity mapping (PLAN) would never actually exercise the
    # shadow pass. `bridge_block`/`peer_block` are "" here (the slim path
    # never builds them) and `session_skills` is "" (never called in this
    # path either) — both match this function's own real values, not
    # placeholders. `recent_msgs=messages` (the full, untrimmed/undeduped
    # history) is a lower-fidelity stand-in: this path builds its own
    # human-only summary (`recent_block`) instead of a per-message list, so
    # there's no already-trimmed message list to reuse here the way the
    # full path has one.
    if env_bool("AGENT_LAB_CONTEXT_RECIPE"):
        from agent_lab.context.bundle_shadow import shadow_compare_bundle
        from agent_lab.run.meta import stamp_run_meta

        try:
            shadow_result = shadow_compare_bundle(
                run_meta=run_meta,
                agent=agent,
                topic=topic,
                plan_md=plan_md,
                parallel_round=2,
                session_guidance=session_guidance,
                session_skills="",
                resume_block=resume_block,
                plugin_block=plugin_block,
                cap_block=cap_block,
                team_block=team_block,
                objection_block=objection_block,
                challenge_block=challenge_block,
                plan_open=plan_open,
                turn_state_block=turn_state_block,
                bridge_block="",
                peer_block="",
                guidance_parts=guidance_parts,
                envelope_block=follow_up,
                tool_rules=tool_rules,
                recent_msgs=messages,
                legacy_bundle=bundle,
            )
            if run_meta is not None and shadow_result is not None:
                stamp_run_meta(run_meta, context_recipe_shadow=shadow_result)
        except Exception:
            pass  # shadow instrumentation must never break the live turn
    return bundle


_WISDOM_BLOCK_CAP = 800


def wisdom_in_context_mode() -> str:
    """``AGENT_LAB_WISDOM_IN_CONTEXT`` — auto(기본, route 따름) | 0 | 1 (전역 강제)."""
    raw = (os.getenv("AGENT_LAB_WISDOM_IN_CONTEXT") or "auto").strip().lower()
    return raw if raw in ("auto", "0", "1") else "auto"


def _wisdom_route_allows(run_meta: RunStateLike | None) -> bool:
    mode = wisdom_in_context_mode()
    if mode == "0":
        return False
    if mode == "1":
        return True
    category = (run_meta or {}).get("_turn_category") or {}
    if not isinstance(category, dict):
        return False
    return str(category.get("value") or "") in ("deep", "critical")


def _append_wisdom_search_block(
    constraints: str,
    *,
    topic: str,
    run_meta: RunStateLike | None,
    parallel_round: int,
) -> str:
    """P5 stigmergy 읽기 경로 — wisdom index 상위 히트를 R1 컨텍스트에 주입.

    R1 한정(이후 라운드는 동료 발화가 컨텍스트), deep/critical route에서만
    (auto). 과거 세션의 검증·학습이 미래 토론의 출발점이 되어 루프가 닫힌다.
    """
    if parallel_round != 1 or not run_meta:
        return constraints
    if not _wisdom_route_allows(run_meta):
        return constraints
    folder_raw = run_meta.get("_session_folder")
    if not folder_raw:
        return constraints
    from pathlib import Path

    folder = Path(str(folder_raw))
    if not folder.is_dir():
        return constraints
    try:
        from agent_lab.wisdom.index import search_wisdom_index, wisdom_index_enabled

        if not wisdom_index_enabled(run_meta):
            return constraints
        hits = search_wisdom_index(folder, topic, limit=3)
    except Exception:
        return constraints
    if not hits:
        return constraints
    lines = ["[세션 위즈덤 — 과거 검증·학습 상위 히트]"]
    used = len(lines[0])
    for hit in hits:
        body = str(hit.get("snippet") or hit.get("title") or "").strip()
        if not body:
            continue
        line = f"- ({hit.get('source') or 'wisdom'}) {body}"
        if used + len(line) > _WISDOM_BLOCK_CAP:
            break
        lines.append(line)
        used += len(line)
    if len(lines) == 1:
        return constraints
    return f"{constraints}\n\n" + "\n".join(lines)


_PLAYBOOK_BLOCK_CAP = 600


def _append_playbook_block(
    constraints: str,
    *,
    topic: str,
    parallel_round: int,
) -> str:
    """HS2-2 — active playbook bullets whose description matches the topic,
    injected R1-only (same discipline as ``_append_wisdom_search_block``)."""
    if parallel_round != 1 or not topic.strip():
        return constraints
    try:
        from agent_lab.wisdom.playbook import playbook_bullets_for_topic

        bullets = playbook_bullets_for_topic(topic, k=3)
    except Exception:
        return constraints
    if not bullets:
        return constraints
    lines = ["[플레이북 — 반복 교정 패턴에서 도출된 지침]"]
    used = len(lines[0])
    for bullet in bullets:
        line = f"- {bullet.description} (evidence={bullet.evidence_count})"
        if used + len(line) > _PLAYBOOK_BLOCK_CAP:
            break
        lines.append(line)
        used += len(line)
    if len(lines) == 1:
        return constraints
    return f"{constraints}\n\n" + "\n".join(lines)


def _append_mission_track_c_blocks(
    constraints: str,
    *,
    run_meta: RunStateLike | None,
    plan_md: str,
) -> str:
    from agent_lab.runtime.context import build_mission_wisdom_block
    from agent_lab.repo_tree_context import (
        build_per_dir_agents_block,
        build_repo_tree_block,
    )
    from agent_lab.workspace.md import PER_DIR_AGENTS_GUIDANCE_HEADER

    out = constraints
    mission_wisdom = build_mission_wisdom_block(run_meta)
    if mission_wisdom.strip():
        out = f"{out}\n\n{mission_wisdom.strip()}"
    if env_bool("AGENT_LAB_REPO_MAP"):
        from agent_lab.repo_map import build_repo_map_block

        repo_block = build_repo_map_block(run_meta, plan_md)
    else:
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
    run_meta: RunStateLike | None = None,
    permissions: dict[str, Any] | None = None,
    format_thread: Callable[[str, list[_MessageLike]], str] | None = None,
    all_messages: list[_MessageLike] | None = None,
    efficiency_mode: bool = False,
    slim_context: bool = False,
    consensus_mode: bool = False,
) -> ContextBundle:
    """Build layered context for one agent call (discuss / plan agent rounds)."""
    from agent_lab.context.layers import should_use_mission_slim_bundle

    compact = env_bool("AGENT_LAB_COMMS_COMPACT") and str(
        (run_meta or {}).get("turn_profile") or ""
    ).strip().lower() not in {"divergence", "발산"}
    if should_use_mission_slim_bundle(run_meta) and not (slim_context and efficiency_mode) and not compact:
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

    from agent_lab.context.limits import agent_context_limits, efficiency_limits
    from agent_lab.context.meta import enrich_bundle_meta
    from agent_lab.agents.registry import AgentId, label
    from agent_lab.room.context import (
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
    pin_before = len(pinned_current_turn_messages(messages))
    trimmed, turns_omitted, chars_omitted, pinned_count = prepare_recent_messages(
        messages, efficiency_mode=efficiency_mode, compact=compact
    )
    pin_capped = efficiency_mode and pinned_count < pin_before
    compact_dropped = (not efficiency_mode) and pinned_count < pin_before

    peer_msgs = collect_peer_messages(messages, agent, parallel_round)
    if artifact_only:
        recent_msgs: list[_MessageLike] = []
        peer_deduped = 0
    else:
        recent_msgs, peer_deduped = dedupe_peer_from_recent(trimmed, peer_msgs, compact=compact)

    agreed = extract_agreed_bullets(plan_md)
    open_bullets = extract_open_bullets(plan_md)
    if eff:
        agreed = agreed[: eff.max_agreed_items]
        open_bullets = open_bullets[: eff.max_open_items]
    if run_meta is not None:
        sync_session_meta(
            run_meta,
            topic=topic,
            messages=cast(Any, full),
            plan_md=plan_md,
            permissions=permissions,
        )
    session_guidance = build_session_guidance_block(run_meta, plan_md=plan_md)
    from agent_lab.room.roster_context import active_agents_from_run_meta
    from agent_lab.room.tasks import team_lead as session_team_lead

    active_roster = active_agents_from_run_meta(run_meta)
    constraints = build_constraints_block(
        permission_lines=permission_lines,
        human_gates=extract_human_gates(messages, topic),
        agreed_bullets=agreed,
        status_tags=extract_status_tags(trimmed),
        workspace_lines=_workspace_lines_for_agent(agent, permissions, run_meta),
        active_agents=active_roster,
        team_lead=session_team_lead(run_meta) if run_meta else None,
    )
    if session_guidance.strip():
        constraints = f"{constraints}\n\n{session_guidance.strip()}"
    grounding_block = _format_grounding_block(run_meta, consensus_mode=consensus_mode)
    if grounding_block.strip():
        constraints = f"{constraints}\n\n{grounding_block.strip()}"
    constraints = _append_mission_track_c_blocks(constraints, run_meta=run_meta, plan_md=plan_md)
    constraints = _append_wisdom_search_block(
        constraints,
        topic=topic,
        run_meta=run_meta,
        parallel_round=parallel_round,
    )
    constraints = _append_playbook_block(
        constraints,
        topic=topic,
        parallel_round=parallel_round,
    )
    from agent_lab.skill_drafts import build_session_skills_block

    session_skills = build_session_skills_block(run_meta)
    if session_skills.strip():
        constraints = f"{constraints}\n\n{session_skills.strip()}"
    resume_block = build_agent_thread_resume_block(agent, run_meta)
    if resume_block.strip():
        constraints = f"{constraints}\n\n{resume_block.strip()}"
    plugin_block = build_plugin_allowlist_block(agent, run_meta)
    if plugin_block.strip():
        constraints = f"{constraints}\n\n{plugin_block.strip()}"
    cap_block = capability_preamble_block(agent, run_meta, parallel_round=parallel_round)
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
    snap = PolicyEngine.gate_snapshot(run_meta)
    gate_block = PolicyEngine.format_gate_block(snap)
    if gate_block.strip():
        constraints = f"{constraints}\n\n{gate_block.strip()}"
    plan_open = build_plan_open_block(
        open_bullets=open_bullets,
        stale_line=plan_stale_banner(run_meta),
    )
    turn_state_block = "" if artifact_only else render_turn_state_block((run_meta or {}).get("turn_state"))
    if artifact_only:
        bridge_block = ""
        recent_block, has_user_in_recent = _build_human_only_recent_block(topic, messages)
        line_range = ""
        peer_block = ""
    else:
        has_user_in_recent = any(m.role == "user" for m in recent_msgs)
        bridge_block = build_turn_bridge_block(messages, parallel_round=parallel_round)
        recent_block, line_range = build_recent_turns_block(
            topic=topic,
            messages=recent_msgs,
            format_thread=thread_fmt,
            all_messages=full,
            turns_omitted=turns_omitted,
            chars_omitted=chars_omitted,
            peer_deduped=peer_deduped,
            compact_dropped=compact_dropped,
            numbered=limits.numbered_context,
        )
        peer_block = format_peer_block(peer_msgs, compact=compact)

    connect_hint = AGENT_CONNECT_HINT.get(agent, "").strip()
    profile = str((run_meta or {}).get("turn_profile") or "").strip().lower()
    reply_policy = apply_inbox_fork_grace_policy(
        resolve_reply_policy(
            parallel_round=parallel_round,
            review_mode=review_mode,
            consensus_mode=consensus_mode,
            turn_profile=profile,
            efficiency_mode=efficiency_mode,
        ),
        run_meta,
    )
    guidance_parts = build_guidance_parts(reply_policy, run_meta=run_meta, agent=agent, active_agents=active_roster)
    if profile == "analyze":
        guidance_parts.insert(
            0,
            "[Analyze turn] Observe and report risks only. Do not use PROPOSE/ENDORSE/BLOCK envelope acts.",
        )
    elif profile in {"divergence", "발산"}:
        from agent_lab.agents.prompts import DIVERGENCE_INSTRUCTION

        guidance_parts.insert(0, DIVERGENCE_INSTRUCTION)
    from agent_lab.room.dispatch_intents import build_dispatch_intent_block

    dispatch_block = build_dispatch_intent_block(run_meta, agent)
    if dispatch_block.strip():
        guidance_parts.append(dispatch_block.strip())
    guidance_block = "---\n" + "\n".join(guidance_parts) + f"\n---\nRespond as {label(cast(AgentId, agent))} only."

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
        from agent_lab.role_plan import review_follow_up_uses_role_persona

        if (
            review_mode
            and parallel_round >= 2
            and review_advocate
            and not review_follow_up_uses_role_persona(run_meta, str(review_advocate))
        ):
            if agent == review_advocate:
                follow_up += "\n[쟁점 검토 — 반박] 1라운드 주장 중 가장 약한 가정 하나를 골라 반박하세요."
            else:
                follow_up += (
                    f"\n[쟁점 검토 — 검토] {label(cast(AgentId, review_advocate))}의 반박에 답하세요(인정 또는 반론)."
                )
        elif parallel_round >= 2:
            follow_up += (
                "\n2라운드(순차 · 토론): 동료 의견을 **이어가거나 보완**하세요. "
                "**또는** 실질적으로 다른 대안·리스크 1건을 CHALLENGE로 제기하세요. "
                "빨리 합의하는 것이 목표가 아닙니다 — 결과를 바꾸는 이견이 가치입니다."
            )

    tool_rules = agent_tool_rules(agent, run_meta, active_agents=active_roster)

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
        recent_max_chars=(ARTIFACT_ONLY_RECENT_MAX_CHARS if artifact_only else None),
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
        "guidance_block": len(guidance_block),
        "connect_hint": len(connect_hint),
        "claude_tools": len(tool_rules),
        "follow_up": len(follow_up),
        "total": len(bundle.render()),
    }
    meta.line_range = line_range
    enrich_bundle_meta(
        meta,
        bundle,
        messages_in_payload=(1 if artifact_only and has_user_in_recent else len(recent_msgs)),
        messages_in_turn=current_turn_message_count(full),
        messages_in_session=count_messages(full),
    )
    _record_context_bundle_metrics(run_meta, meta, agent=agent, mode="full")
    # CX8 (09-context-engineering.md §11) — flag-gated shadow-parity pass.
    # Default off: this `env_bool` check is the entire cost when disabled.
    # When on, computes a parallel select_context()-based manifest from
    # values already computed above and records a comparison for later
    # dogfood/eval review — never changes `bundle` itself. See
    # context/bundle_shadow.py's module docstring for exactly what this
    # does and does not cover.
    if env_bool("AGENT_LAB_CONTEXT_RECIPE"):
        from agent_lab.context.bundle_shadow import shadow_compare_bundle
        from agent_lab.run.meta import stamp_run_meta

        try:
            shadow_result = shadow_compare_bundle(
                run_meta=run_meta,
                agent=agent,
                topic=topic,
                plan_md=plan_md,
                parallel_round=parallel_round,
                session_guidance=session_guidance,
                session_skills=session_skills,
                resume_block=resume_block,
                plugin_block=plugin_block,
                cap_block=cap_block,
                team_block=team_block,
                objection_block=objection_block,
                challenge_block=challenge_block,
                plan_open=plan_open,
                turn_state_block=turn_state_block,
                bridge_block=bridge_block,
                peer_block=peer_block,
                guidance_parts=guidance_parts,
                envelope_block=envelope_block,
                tool_rules=tool_rules,
                recent_msgs=recent_msgs,
                legacy_bundle=bundle,
            )
            if run_meta is not None and shadow_result is not None:
                stamp_run_meta(run_meta, context_recipe_shadow=shadow_result)
        except Exception:
            pass  # shadow instrumentation must never break the live turn
    return bundle


def _record_context_bundle_metrics(
    run_meta: RunStateLike | None,
    meta: Any,
    *,
    agent: str,
    mode: str,
) -> None:
    if run_meta is None or not hasattr(run_meta, "get"):
        return
    row = meta.to_dict() if hasattr(meta, "to_dict") else {}
    row["agent"] = agent
    row["mode"] = mode
    # F7 dogfood signals — env checks only (no repo_map import on OFF path).
    repo_map_on = (os.getenv("AGENT_LAB_REPO_MAP") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    compact_on = (os.getenv("AGENT_LAB_COMPACT_TOOL_OUTPUT") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    row["repo_layer"] = "repo_map" if repo_map_on else "repo_tree"
    row["repo_map_enabled"] = repo_map_on
    row["compact_tool_output"] = compact_on
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, last_context_bundle=row)
    log = list(run_meta.get("context_quality_log") or [])
    log.append(
        {
            "agent": agent,
            "mode": mode,
            "repo_layer": row["repo_layer"],
            "budget_pct": row.get("budget_pct"),
            "trim_level": row.get("trim_level"),
            "chars_omitted": row.get("chars_omitted"),
            "compact_tool_output": compact_on,
        }
    )
    stamp_run_meta(run_meta, context_quality_log=log[-20:])
