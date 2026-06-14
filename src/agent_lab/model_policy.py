from __future__ import annotations

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
    team_ready: bool
    loop_ready: bool
    loop_blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LoopReadinessFailure:
    agents: tuple[str, ...]
    reason: str


def team_ready(profile: ModelProfile) -> bool:
    return bool(profile.model_id)


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


def model_readiness(agent_id: str) -> ModelReadiness | None:
    known = _known_agent_id(agent_id)
    if known is None:
        return None
    profile = agent_model_profiles()[known]
    blockers = loop_blockers(profile)
    return ModelReadiness(
        provider=profile.provider,
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
