from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence
from typing import Literal

from agent_lab import agent_models

AgentId = Literal["cursor", "codex", "claude"]
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
    return tuple(blockers)


def loop_ready(profile: ModelProfile) -> bool:
    return not loop_blockers(profile)


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


def resolve_runtime_model_id(agent_id: str) -> str:
    """Resolve configured model id for an agent (env override aware)."""
    match agent_id.strip().lower():
        case "cursor":
            return (os.getenv("CURSOR_MODEL") or agent_models.DEFAULT_CURSOR_MODEL).strip()
        case "codex":
            return (os.getenv("CODEX_MODEL") or agent_models.DEFAULT_CODEX_MODEL).strip()
        case "claude":
            return (os.getenv("CLAUDE_MODEL") or agent_models.DEFAULT_CLAUDE_MODEL).strip()
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


def register_model_profile(profile: ModelProfile) -> None:
    """Register or override a model profile after loop-capability eval."""
    _MODEL_PROFILE_REGISTRY[_profile_registry_key(profile.agent, profile.model_id)] = profile


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


def model_profile_for(agent_id: str, *, model_id: str | None = None) -> ModelProfile | None:
    known = _known_agent_id(agent_id)
    if known is None:
        return None
    mid = (model_id or resolve_runtime_model_id(agent_id)).strip()
    if not mid:
        return _unknown_model_profile(known, "")
    key = _profile_registry_key(known, mid)
    if key in _MODEL_PROFILE_REGISTRY:
        return _MODEL_PROFILE_REGISTRY[key]
    default = agent_model_profiles()[known]
    if mid.lower() == default.model_id.strip().lower():
        return default
    return _unknown_model_profile(known, mid)


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


def loop_readiness_failure(agent_ids: Sequence[str]) -> LoopReadinessFailure | None:
    not_ready: list[str] = []
    for agent_id in agent_ids:
        readiness = model_readiness(agent_id)
        if readiness is not None and not readiness.loop_ready:
            not_ready.append(agent_id.strip().lower())
    if not not_ready:
        return None
    return LoopReadinessFailure(
        agents=tuple(not_ready),
        reason="selected agent model lacks question/tool capability for Loop",
    )
