"""Reply format policy — when envelope/guidance blocks apply (Hook · Communicate reform)."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any

from agent_lab.agent_envelope import (
    ENVELOPE_FORMAT_GUIDANCE,
    envelope_act,
    envelope_protocol_block,
    is_endorse_reply,
)
from agent_lab.inbox_harvest import inbox_pause_grace_guidance, inbox_pause_grace_pending
from agent_lab.room_context import (
    ANALYSIS_TURN_GUIDANCE,
    CONVERSATION_GUIDANCE,
    EFFICIENCY_RESPONSE_GUIDANCE,
    MULTI_AGENT_COORDINATION,
    PEER_DECISION_GUIDANCE,
)

DISPATCH_LEAD_GUIDANCE = (
    "[턴 리드 · dispatch]\n"
    "동료에게 scoped work를 내릴 때 envelope `act: MESSAGE`, `to: <agent>`, "
    'optional `dispatch: { "op": "scoped", "prompt": "…" }` 를 사용하세요. '
    "실행은 Human `DELEGATE`/`DISPATCH` 또는 명시 GO 후에만 됩니다."
)


def envelope_strict_env() -> str:
    return (os.getenv("AGENT_LAB_ENVELOPE_STRICT") or "consensus_only").strip().lower()


def legacy_endorse_enabled() -> bool:
    """Phrase-only 「이의 없습니다」 endorse fallback (opt-in; default off)."""
    raw = (os.getenv("AGENT_LAB_LEGACY_ENDORSE") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def guidance_tier_env() -> str:
    return (os.getenv("AGENT_LAB_GUIDANCE_TIER") or "standard").strip().lower()


@dataclass(frozen=True)
class ReplyPolicy:
    parallel_round: int
    review_mode: bool
    consensus_mode: bool
    turn_profile: str
    efficiency_mode: bool
    envelope_strict: bool
    envelope_warn: bool
    inject_envelope_guidance: bool
    inject_decision_fork: bool
    inject_efficiency: bool
    inject_analysis: bool
    inject_conversation: bool
    inject_coordination: bool
    inject_peer_decision: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "parallel_round": self.parallel_round,
            "review_mode": self.review_mode,
            "consensus_mode": self.consensus_mode,
            "turn_profile": self.turn_profile,
            "efficiency_mode": self.efficiency_mode,
            "envelope_strict": self.envelope_strict,
            "envelope_warn": self.envelope_warn,
        }


def resolve_reply_policy(
    *,
    parallel_round: int = 1,
    review_mode: bool = False,
    consensus_mode: bool = False,
    turn_profile: str | None = None,
    efficiency_mode: bool = False,
) -> ReplyPolicy:
    """Profile combination priority: consensus > review R2+ > analyze > base discuss."""
    profile = str(turn_profile or "").strip().lower()
    strict_mode = envelope_strict_env()
    r2 = max(1, parallel_round) >= 2

    envelope_strict = False
    envelope_warn = False
    inject_envelope = False
    inject_fork = False

    if consensus_mode and r2:
        inject_envelope = True
        inject_fork = True
        if strict_mode in ("always", "consensus_only", "1", "true", "yes", "on"):
            envelope_strict = True
        elif strict_mode in ("off", "0", "false", "no"):
            envelope_strict = False
            envelope_warn = True
        else:
            envelope_strict = True
    elif review_mode and r2:
        inject_envelope = True
        inject_fork = True
        if strict_mode == "always":
            envelope_strict = True
        else:
            envelope_warn = True
    elif r2 and strict_mode == "always":
        inject_envelope = True
        envelope_strict = True
    elif r2:
        inject_envelope = True
        envelope_warn = True

    inject_analysis = profile in ("analyze", "discuss")
    inject_efficiency = bool(efficiency_mode)

    tier = guidance_tier_env()
    inject_conversation = tier != "minimal"
    inject_coordination = tier in ("standard", "debug")
    inject_peer = tier in ("standard", "debug")
    if profile == "quick":
        inject_conversation = False
        inject_coordination = False
        inject_peer = False
        inject_analysis = False

    return ReplyPolicy(
        parallel_round=max(1, parallel_round),
        review_mode=review_mode,
        consensus_mode=consensus_mode,
        turn_profile=profile,
        efficiency_mode=inject_efficiency,
        envelope_strict=envelope_strict,
        envelope_warn=envelope_warn and not envelope_strict,
        inject_envelope_guidance=inject_envelope,
        inject_decision_fork=inject_fork,
        inject_efficiency=inject_efficiency,
        inject_analysis=inject_analysis,
        inject_conversation=inject_conversation,
        inject_coordination=inject_coordination,
        inject_peer_decision=inject_peer,
    )


def build_guidance_parts(
    policy: ReplyPolicy,
    *,
    run_meta: dict[str, Any] | None = None,
    agent: str = "",
) -> list[str]:
    from agent_lab.room_preset import is_fast_room_session

    parts: list[str] = []
    if run_meta:
        from agent_lab.response_contracts import response_contract_guidance

        contract_guidance = response_contract_guidance(run_meta)
        if contract_guidance:
            parts.append(contract_guidance)
    if run_meta and agent:
        from agent_lab.room_tasks import team_lead

        if str(agent).strip().lower() == team_lead(run_meta):
            parts.append(DISPATCH_LEAD_GUIDANCE)
        from agent_lab.role_plan import persona_for_agent

        role_text = persona_for_agent(run_meta.get("_turn_roles"), agent)
        if role_text:
            parts.append(role_text)
    if run_meta and inbox_pause_grace_pending(run_meta):
        parts.append(inbox_pause_grace_guidance(run_meta))
    if policy.inject_analysis and policy.turn_profile in ("analyze", "discuss"):
        parts.append(ANALYSIS_TURN_GUIDANCE.strip())
    if run_meta and is_fast_room_session(run_meta):
        from agent_lab.room_context import FAST_TURN_GUIDANCE

        if FAST_TURN_GUIDANCE.strip() not in parts:
            parts.insert(0, FAST_TURN_GUIDANCE.strip())
    if policy.turn_profile == "specialist":
        parts.append("[Specialist turn · R1 Codex+Claude → R2 Cursor patch. Stay in your capability lane.]")
    if policy.turn_profile == "verified":
        from agent_lab.verified_loop import VERIFIED_LOOP_GUIDANCE

        parts.append(VERIFIED_LOOP_GUIDANCE)
    if policy.inject_conversation:
        parts.append(CONVERSATION_GUIDANCE)
    if policy.inject_coordination:
        parts.append(MULTI_AGENT_COORDINATION)
    if policy.inject_peer_decision:
        parts.append(PEER_DECISION_GUIDANCE)
    if policy.inject_efficiency:
        parts.append(EFFICIENCY_RESPONSE_GUIDANCE)
    return parts


def apply_inbox_pause_grace_policy(
    policy: ReplyPolicy,
    run_meta: dict[str, Any] | None,
) -> ReplyPolicy:
    if inbox_pause_grace_pending(run_meta):
        return replace(policy, inject_decision_fork=False)
    return policy


apply_inbox_fork_grace_policy = apply_inbox_pause_grace_policy


def envelope_follow_up_block(policy: ReplyPolicy, *, context: str = "discuss") -> str:
    if not policy.inject_envelope_guidance:
        return ""
    compact = guidance_tier_env() != "debug"
    labels = {
        "consensus": "자유 토론 · 합의 확인 R2+",
        "review": "리뷰 · R2+ 순차",
        "discuss": "회의 · R2+ 순차 (동료 답변 반영)",
    }
    label = labels.get(context, context)
    if policy.inject_decision_fork:
        return envelope_protocol_block(context=context, compact=compact)
    if compact:
        from agent_lab.agent_envelope import ENVELOPE_FORMAT_GUIDANCE_SHORT

        return f"{ENVELOPE_FORMAT_GUIDANCE_SHORT}\n(Context: {label})"
    return f"{ENVELOPE_FORMAT_GUIDANCE}\n(Context: {label})"


def summarize_turn_communicate_meta(
    turn_messages: list[Any],
    context_log: list[dict[str, Any]] | None,
    *,
    policy: ReplyPolicy | None = None,
) -> dict[str, Any]:
    guidance_chars = 0
    if context_log:
        for entry in context_log:
            layer = (entry.get("layer_chars") or {}) if isinstance(entry, dict) else {}
            guidance_chars += int(layer.get("guidance_block") or 0)

    legacy_endorse = 0
    parse_errors = 0
    agent_replies = 0
    act_counts: dict[str, int] = {}
    acts_by_round: dict[str, dict[str, int]] = {}
    for m in turn_messages:
        if getattr(m, "role", None) != "agent":
            continue
        agent_replies += 1
        body = getattr(m, "content", "") or ""
        env = getattr(m, "envelope", None)
        if legacy_endorse_enabled() and is_endorse_reply(body, env) and not env:
            legacy_endorse += 1
        if getattr(m, "envelope_parse_error", False):
            parse_errors += 1
        act = envelope_act(env if isinstance(env, dict) else None)
        if act:
            act_counts[act] = act_counts.get(act, 0) + 1
            round_key = str(getattr(m, "parallel_round", None) or 1)
            per_round = acts_by_round.setdefault(round_key, {})
            per_round[act] = per_round.get(act, 0) + 1

    meta: dict[str, Any] = {
        "envelope_strict": bool(policy.envelope_strict) if policy else False,
        "envelope_parse_error_count": parse_errors,
        "guidance_chars": guidance_chars,
        "legacy_endorse_count": legacy_endorse,
        "agent_reply_count": agent_replies,
    }
    if act_counts:
        meta["act_counts"] = act_counts
        meta["acts_by_round"] = acts_by_round
    if policy:
        meta["reply_policy"] = policy.to_dict()
    return meta
