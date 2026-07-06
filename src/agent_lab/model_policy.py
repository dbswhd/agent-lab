from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from typing import Literal

from agent_lab.agent import models as agent_models

AgentId = Literal["cursor", "codex", "claude", "kimi", "kimi_work", "local"]
ProviderId = Literal["local", "openai", "anthropic"]
Tier = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class ModelProfile:
    provider: ProviderId
    model_id: str
    agent: AgentId
    supports_tools: bool
    supports_inbox_mcp: bool
    supports_json_envelope: bool
    supports_long_context: bool
    cost_tier: Tier
    latency_tier: Tier


@dataclass(frozen=True, slots=True)
class ModelReadiness:
    provider: ProviderId
    model_id: str
    team_ready: bool
    loop_ready: bool
    loop_blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LoopReadinessFailure:
    agents: tuple[str, ...]
    reason: str


def team_ready(profile: ModelProfile) -> bool:
    return bool(profile.model_id.strip())


def loop_blockers(profile: ModelProfile) -> tuple[str, ...]:
    blockers: list[str] = []
    if not profile.supports_tools:
        blockers.append("supports_tools")
    if not profile.supports_inbox_mcp:
        blockers.append("supports_inbox_mcp")
    if not profile.supports_json_envelope:
        blockers.append("supports_json_envelope")
    if profile.agent == "kimi_work":
        from agent_lab.kimi.work_loop import kimi_work_loop_waives_inbox_mcp

        if kimi_work_loop_waives_inbox_mcp():
            blockers = [b for b in blockers if b != "supports_inbox_mcp"]
    return tuple(blockers)


def loop_ready(profile: ModelProfile) -> bool:
    return not loop_blockers(profile)


LOOP_BLOCKER_LABELS: dict[str, str] = {
    "supports_tools": "tools/MCP (daimon·CLI capability probe)",
    "supports_inbox_mcp": "Human Inbox MCP (inbox bridge)",
    "supports_json_envelope": "structured JSON envelope (Loop consensus act)",
}


def loop_blocker_label(code: str) -> str:
    return LOOP_BLOCKER_LABELS.get(code.strip(), code.strip())


def loop_readiness_agent_detail(agent_id: str) -> dict[str, object]:
    """Per-agent Loop gate diagnostics for API 422 detail payloads."""
    aid = agent_id.strip().lower()
    readiness = model_readiness(aid)
    blockers = list(readiness.loop_blockers) if readiness is not None else []
    labels = [loop_blocker_label(code) for code in blockers]
    if readiness is None:
        summary = "agent profile not recognised — live loop probe did not run"
    elif not blockers:
        summary = "loop-ready"
    else:
        summary = "missing: " + ", ".join(labels)
    return {
        "id": aid,
        "loop_ready": bool(readiness.loop_ready) if readiness is not None else False,
        "loop_blockers": blockers,
        "blocker_labels": labels,
        "model_id": readiness.model_id if readiness is not None else None,
        "summary": summary,
    }


def loop_readiness_failure_detail(agent_ids: Sequence[str]) -> dict[str, object] | None:
    """Structured Loop readiness failure for HTTP 422 (None when all ready)."""
    failure = loop_readiness_failure(agent_ids)
    if failure is None:
        return None
    agents = list(failure.agents)
    details = [loop_readiness_agent_detail(aid) for aid in agents]
    hint_parts: list[str] = []
    blocked_ids = {str(d.get("id") or "") for d in details}
    if "kimi_work" in blocked_ids:
        hint_parts.append("Kimi Work: rail 「연결」에서 재연결")
        hint_parts.append(
            "daimon inbox feature 미 advertise 시 AGENT_LAB_KIMI_WORK_LOOP_PHASE=1 로 inbox gate 완화 가능"
        )
    if len(agent_ids) > len(agents):
        capable = [a for a in agent_ids if str(a).strip().lower() not in blocked_ids]
        if capable:
            hint_parts.append(
                f"Loop-ready agent만 보내려면 @{' @'.join(capable)} 멘션 또는 roster에서 미준비 agent 제외"
            )
    elif len(agent_ids) > 1 and blocked_ids:
        hint_parts.append("roster에서 loop_ready=false agent를 빼거나 capable agent만 @-mention 하세요")
    return {
        "code": "loop_readiness_failed",
        "message": "loop model readiness failed",
        "agents": agents,
        "reason": failure.reason,
        "agent_details": details,
        "hint": " · ".join(hint_parts) if hint_parts else None,
    }


def _tier(raw: object, default: Tier) -> Tier:
    value = str(raw or default).strip().lower()
    if value in ("low", "medium", "high"):
        return value  # type: ignore[return-value]
    return default


SUBSTITUTE_AGENT_IDS: frozenset[str] = frozenset({"kimi", "kimi_work", "local"})


def _known_agent_id(agent_id: str) -> AgentId | None:
    match agent_id.strip().lower():
        case "cursor":
            return "cursor"
        case "codex":
            return "codex"
        case "claude":
            return "claude"
        case _:
            return None


def _substitute_agent_id(agent_id: str) -> AgentId | None:
    """Recognise kimi / kimi_work / local as substitute agents (not in default profiles)."""
    raw = agent_id.strip().lower()
    if raw in SUBSTITUTE_AGENT_IDS:
        return raw  # type: ignore[return-value]
    return None


def _substitute_profile(agent: AgentId, model_id: str) -> ModelProfile:
    """Conservative profile for substitute agents: team-ready, NOT loop-ready.

    Substitutes must earn loop-readiness via a live capability probe (stage-2).
    """
    provider: ProviderId = "local"
    return ModelProfile(
        provider=provider,
        model_id=model_id or "default",
        agent=agent,
        supports_tools=False,
        supports_inbox_mcp=False,
        supports_json_envelope=False,
        supports_long_context=False,
        cost_tier="low",
        latency_tier="medium",
    )


def resolve_runtime_model_id(agent_id: str) -> str:
    """Resolve configured model id for an agent (env override aware)."""
    match agent_id.strip().lower():
        case "cursor":
            return (os.getenv("CURSOR_MODEL") or agent_models.DEFAULT_CURSOR_MODEL).strip()
        case "codex":
            return (os.getenv("CODEX_MODEL") or agent_models.DEFAULT_CODEX_MODEL).strip()
        case "claude":
            return (os.getenv("CLAUDE_MODEL") or agent_models.DEFAULT_CLAUDE_MODEL).strip()
        case "kimi":
            return (os.getenv("KIMI_MODEL") or "kimi-default").strip()
        case "kimi_work":
            from agent_lab.kimi.work_provider import kimi_work_model

            return kimi_work_model()
        case "local":
            return (os.getenv("LOCAL_MODEL") or "local-default").strip()
        case _:
            return ""


def _profile_registry_key(agent: AgentId, model_id: str) -> str:
    return f"{agent}:{model_id.strip().lower()}"


def agent_model_profiles() -> dict[AgentId, ModelProfile]:
    return {
        "cursor": ModelProfile(
            provider="local",
            model_id=agent_models.DEFAULT_CURSOR_MODEL,
            agent="cursor",
            # Cursor is the primary execution agent (file/UI/build, specialist R2)
            # and mounts the inbox MCP at runtime (cursor_inbox_mcp.mount_inbox_mcp_when_requested),
            # so it is tool- and inbox-capable. JSON envelope is honored.
            supports_tools=True,
            supports_inbox_mcp=True,
            supports_json_envelope=True,
            supports_long_context=False,
            cost_tier="low",
            latency_tier="medium",
        ),
        "codex": ModelProfile(
            provider="openai",
            model_id=agent_models.DEFAULT_CODEX_MODEL,
            agent="codex",
            supports_tools=True,
            supports_inbox_mcp=True,
            supports_json_envelope=True,
            supports_long_context=True,
            cost_tier="high",
            latency_tier="medium",
        ),
        "claude": ModelProfile(
            provider="anthropic",
            model_id=agent_models.DEFAULT_CLAUDE_MODEL,
            agent="claude",
            supports_tools=True,
            supports_inbox_mcp=True,
            supports_json_envelope=True,
            supports_long_context=True,
            cost_tier="high",
            latency_tier="medium",
        ),
    }


def _build_default_registry() -> dict[str, ModelProfile]:
    registry: dict[str, ModelProfile] = {}
    for agent, profile in agent_model_profiles().items():
        registry[_profile_registry_key(agent, profile.model_id)] = profile
    return registry


_MODEL_PROFILE_REGISTRY: dict[str, ModelProfile] = _build_default_registry()
_LOOP_EVAL_LOADED = False


def _loop_eval_registry_path() -> Path:
    from agent_lab.workspace.roots import project_root

    override = (os.getenv("AGENT_LAB_LOOP_EVAL_REGISTRY") or "").strip()
    if override:
        return Path(override).expanduser()
    return project_root() / ".agent-lab" / "loop_model_eval.json"


def load_loop_eval_registry(*, force: bool = False) -> int:
    """Load loop-capability eval results from disk into the profile registry."""
    global _LOOP_EVAL_LOADED
    if _LOOP_EVAL_LOADED and not force:
        return 0
    path = _loop_eval_registry_path()
    if not path.is_file():
        _LOOP_EVAL_LOADED = True
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _LOOP_EVAL_LOADED = True
        return 0
    rows = raw.get("profiles") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        _LOOP_EVAL_LOADED = True
        return 0
    loaded = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        agent = str(row.get("agent") or "").strip().lower()
        model_id = str(row.get("model_id") or "").strip()
        if agent not in ("cursor", "codex", "claude", "kimi", "kimi_work", "local") or not model_id:
            continue
        provider = str(row.get("provider") or "local").strip().lower()
        if provider not in ("local", "openai", "anthropic"):
            provider = "local"
        profile = ModelProfile(
            provider=provider,  # type: ignore[arg-type]
            model_id=model_id,
            agent=agent,  # type: ignore[arg-type]
            supports_tools=bool(row.get("supports_tools")),
            supports_inbox_mcp=bool(row.get("supports_inbox_mcp")),
            supports_json_envelope=bool(row.get("supports_json_envelope")),
            supports_long_context=bool(row.get("supports_long_context")),
            cost_tier=_tier(row.get("cost_tier"), "medium"),
            latency_tier=_tier(row.get("latency_tier"), "medium"),
        )
        register_model_profile(profile)
        loaded += 1
    _LOOP_EVAL_LOADED = True
    return loaded


def _ensure_loop_eval_loaded() -> None:
    load_loop_eval_registry()


def register_model_profile(profile: ModelProfile) -> None:
    """Register or override a model profile after loop-capability eval."""
    _MODEL_PROFILE_REGISTRY[_profile_registry_key(profile.agent, profile.model_id)] = profile


def invalidate_model_profile(agent_id: str, *, model_id: str | None = None) -> None:
    """Drop a cached in-process profile so the next readiness check re-probes."""
    aid = agent_id.strip().lower()
    mid = (model_id or resolve_runtime_model_id(aid)).strip()
    if not aid or not mid:
        return
    _MODEL_PROFILE_REGISTRY.pop(_profile_registry_key(aid, mid), None)


def _unknown_model_profile(agent: AgentId, model_id: str) -> ModelProfile:
    """Conservative profile for unregistered models: Team-ready, not Loop-ready."""
    provider: ProviderId = "local" if agent == "cursor" else ("openai" if agent == "codex" else "anthropic")
    return ModelProfile(
        provider=provider,
        model_id=model_id,
        agent=agent,
        supports_tools=False,
        supports_inbox_mcp=False,
        supports_json_envelope=False,
        supports_long_context=False,
        cost_tier="low" if provider == "local" else "medium",
        latency_tier="medium",
    )


def loop_cost_tier_blocks(profile: ModelProfile) -> bool:
    from agent_lab.turn_modes import loop_max_cost_tier

    rank = {"low": 0, "medium": 1, "high": 2}
    max_tier = loop_max_cost_tier()
    return rank.get(profile.cost_tier, 2) > rank.get(max_tier, 2)


def model_profile_for(agent_id: str, *, model_id: str | None = None) -> ModelProfile | None:
    _ensure_loop_eval_loaded()
    known = _known_agent_id(agent_id)
    if known is not None:
        mid = (model_id or resolve_runtime_model_id(agent_id)).strip()
        if not mid:
            return _unknown_model_profile(known, "")
        key = _profile_registry_key(known, mid)
        if key in _MODEL_PROFILE_REGISTRY:
            return _MODEL_PROFILE_REGISTRY[key]
        default = agent_model_profiles()[known]
        if mid.lower() == default.model_id.strip().lower():
            return default
        from agent_lab.model_policy_probe import loop_probe_enabled, probe_loop_capabilities_cached

        if loop_probe_enabled():
            probed = probe_loop_capabilities_cached(agent_id, mid)
            if probed is not None:
                return probed
        return _unknown_model_profile(known, mid)

    # Substitute agents (kimi, kimi_work, local) — not in default profiles.
    sub = _substitute_agent_id(agent_id)
    if sub is not None:
        mid = (model_id or resolve_runtime_model_id(agent_id)).strip() or "default"
        from agent_lab.model_policy_probe import loop_probe_enabled, probe_loop_capabilities_cached

        # Registry entries for substitutes are always probe-derived, so only
        # consult the registry when the probe gate is open (avoids stale
        # live-probed entries being returned when probe is disabled).
        if loop_probe_enabled():
            key = _profile_registry_key(sub, mid)
            if key in _MODEL_PROFILE_REGISTRY:
                return _MODEL_PROFILE_REGISTRY[key]
            probed = probe_loop_capabilities_cached(agent_id, mid)
            if probed is not None:
                return probed
        return _substitute_profile(sub, mid)

    return None


def model_readiness(agent_id: str, *, model_id: str | None = None) -> ModelReadiness | None:
    profile = model_profile_for(agent_id, model_id=model_id)
    if profile is None:
        return None
    blockers = loop_blockers(profile)
    return ModelReadiness(
        provider=profile.provider,
        model_id=profile.model_id,
        team_ready=team_ready(profile),
        loop_ready=not blockers,
        loop_blockers=blockers,
    )


def preferred_cost_tier_for_category(category: str) -> Tier | None:
    """CategoryRoute 카테고리에 따른 에이전트 비용 티어 상한.

    quick → low만 허용 (빠른 단순 작업에 고비용 에이전트 낭비 방지).
    그 외 → None (제약 없음, 전원 참여).
    """
    if category == "quick":
        return "low"
    return None


def agents_within_cost_tier(
    agent_ids: list[str],
    max_tier: Tier,
) -> list[str]:
    """max_tier 이하 비용 에이전트만 반환. 전원 필터되면 원본 반환(폴백).

    cost_tier가 없는 에이전트(프로필 미등록)는 포함시킨다.
    """
    rank: dict[Tier, int] = {"low": 0, "medium": 1, "high": 2}
    cap = rank.get(max_tier, 2)
    filtered: list[str] = []
    for aid in agent_ids:
        profile = model_profile_for(aid)
        if profile is None:
            filtered.append(aid)
            continue
        if rank.get(profile.cost_tier, 2) <= cap:
            filtered.append(aid)
    return filtered if filtered else list(agent_ids)


def partition_loop_capable_agents(
    agent_ids: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split *agent_ids* into Loop-capable vs blocked agents (order preserved)."""
    capable: list[str] = []
    incapable: list[str] = []
    for agent_id in agent_ids:
        aid = str(agent_id).strip().lower()
        if not aid:
            continue
        readiness = model_readiness(aid)
        if readiness is None:
            incapable.append(aid)
            continue
        profile = model_profile_for(aid)
        if profile is not None and loop_cost_tier_blocks(profile):
            incapable.append(aid)
            continue
        if not readiness.loop_ready:
            incapable.append(aid)
            continue
        capable.append(aid)
    return tuple(capable), tuple(incapable)


def loop_readiness_failure(agent_ids: Sequence[str]) -> LoopReadinessFailure | None:
    from agent_lab.turn_modes import loop_max_cost_tier

    not_ready: list[str] = []
    cost_blocked: list[str] = []
    unvalidated: list[str] = []
    for agent_id in agent_ids:
        readiness = model_readiness(agent_id)
        if readiness is None:
            # Fail-closed: unknown/unrecognised agents cannot be loop-ready.
            unvalidated.append(agent_id.strip().lower())
            continue
        profile = model_profile_for(agent_id)
        if profile is not None and loop_cost_tier_blocks(profile):
            cost_blocked.append(agent_id.strip().lower())
            continue
        if not readiness.loop_ready:
            not_ready.append(agent_id.strip().lower())
    if cost_blocked:
        return LoopReadinessFailure(
            agents=tuple(cost_blocked),
            reason=f"model cost tier exceeds Loop ceiling ({loop_max_cost_tier()})",
        )
    if not_ready:
        return LoopReadinessFailure(
            agents=tuple(not_ready),
            reason="selected agent model lacks question/tool capability for Loop",
        )
    if unvalidated:
        return LoopReadinessFailure(
            agents=tuple(unvalidated),
            reason="selected agent is not recognised or has no validated profile for Loop",
        )
    return None
