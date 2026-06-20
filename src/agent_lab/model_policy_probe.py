from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.model_policy import (
    AgentId,
    ModelProfile,
    ProviderId,
    Tier,
    _known_agent_id,
    _substitute_agent_id,
    _substitute_profile,
    _tier,
    register_model_profile,
    resolve_runtime_model_id,
)

_PROBE_CACHE_LOADED = False


def loop_probe_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_LOOP_PROBE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _live_probe_enabled() -> bool:
    """Flag-gated live capability probe (stage-2). Default OFF for backward compat."""
    raw = (os.getenv("AGENT_LAB_LOOP_PROBE_LIVE") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _probe_cache_path() -> Path:
    from agent_lab.workspace_roots import project_root

    override = (os.getenv("AGENT_LAB_LOOP_PROBE_CACHE") or "").strip()
    if override:
        return Path(override).expanduser()
    return project_root() / ".agent-lab" / "loop_probe_cache.json"


def _mock_mode() -> bool:
    return os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {"1", "true", "yes", "on"}


def _probe_supports_tools(agent: AgentId) -> bool:
    if _mock_mode():
        return True
    match agent:
        case "cursor":
            if (os.getenv("CURSOR_API_KEY") or "").strip():
                return True
            try:
                import cursor_sdk  # noqa: F401

                return True
            except ImportError:
                return False
        case "codex":
            if (os.getenv("OPENAI_API_KEY") or os.getenv("CODEX_API_KEY") or "").strip():
                return True
            try:
                from agent_lab.codex_oauth import codex_oauth_ready

                ok, _ = codex_oauth_ready()
                return bool(ok)
            except Exception:
                return False
        case "claude":
            try:
                from agent_lab import claude_cli

                ok, _ = claude_cli.claude_auth_logged_in()
                return bool(ok)
            except Exception:
                return False
    return False


def _probe_supports_inbox_mcp(agent: AgentId) -> bool:
    from agent_lab.cursor_inbox_mcp import execute_inbox_mcp_enabled, plan_inbox_mcp_enabled

    if not execute_inbox_mcp_enabled() and not plan_inbox_mcp_enabled():
        return False
    if _mock_mode():
        return True
    return agent in ("cursor", "codex", "claude")


def _probe_supports_json_envelope(agent: AgentId) -> bool:
    if _mock_mode():
        return True
    return agent in ("cursor", "codex", "claude")


def _probe_live_capability(agent: AgentId, model_id: str) -> bool:
    """Stage-2: make a minimal real call to verify the agent can respond and produce a structured envelope.

    Returns True only if the agent responds with a non-empty reply that contains
    a parseable JSON envelope (or valid prose when envelope is not requested).
    """
    if _mock_mode():
        return True

    # Only run for agents that have a real provider backend wired.
    if agent in ("kimi", "kimi_work", "local"):
        from agent_lab.agents import registry

        if not registry._is_ready(agent):
            return False
        try:
            reply = registry.call_agent_reply(
                agent,
                system="You are a test probe. Reply with a single JSON object containing {'status': 'ok'}.",
                user="Probe test. Respond with JSON only.",
                request_structured_envelope=True,
            )
            text = reply.text.strip()
            if reply.structured_envelope is not None:
                return True
            # Fallback: try to parse JSON from text
            try:
                parsed = json.loads(text)
                return isinstance(parsed, dict) and "status" in parsed
            except (json.JSONDecodeError, ValueError):
                return False
        except Exception:
            return False

    # For built-in agents (cursor, codex, claude), the infra probe is sufficient
    # unless live probe is explicitly enabled.
    return True


def probe_loop_capabilities(agent_id: str, model_id: str) -> ModelProfile | None:
    """Two-stage probe: infrastructure (stage-1) + optional live capability (stage-2)."""
    agent = _known_agent_id(agent_id)
    if agent is None:
        agent = _substitute_agent_id(agent_id)
    if agent is None:
        return None

    mid = (model_id or resolve_runtime_model_id(agent_id)).strip()
    if not mid:
        return None

    # Stage-1: infrastructure probe
    if agent in ("kimi", "kimi_work", "local"):
        # Substitutes start with a conservative profile.
        profile = _substitute_profile(agent, mid)
    else:
        provider: ProviderId = "local" if agent == "cursor" else ("openai" if agent == "codex" else "anthropic")
        supports_tools = _probe_supports_tools(agent)
        supports_inbox = _probe_supports_inbox_mcp(agent)
        supports_envelope = _probe_supports_json_envelope(agent)
        cost: Tier = "low" if provider == "local" else "high"
        profile = ModelProfile(
            provider=provider,
            model_id=mid,
            agent=agent,
            supports_tools=supports_tools,
            supports_inbox_mcp=supports_inbox,
            supports_json_envelope=supports_envelope,
            supports_long_context=provider != "local",
            cost_tier=cost,
            latency_tier="medium",
        )

    # Stage-2: live capability probe (flag-gated, default off for built-ins, always on for substitutes)
    if agent in ("kimi", "kimi_work", "local") or _live_probe_enabled():
        live_ok = _probe_live_capability(agent, mid)
        if not live_ok:
            # Downgrade: force not-loop-ready
            profile = replace(
                profile,
                supports_tools=False,
                supports_inbox_mcp=False,
                supports_json_envelope=False,
            )
        else:
            # Upgrade substitutes to loop-ready if they pass live probe
            if agent in ("kimi", "kimi_work", "local"):
                profile = replace(
                    profile,
                    supports_tools=True,
                    supports_inbox_mcp=True,
                    supports_json_envelope=True,
                )

    return profile


def _load_probe_cache() -> dict[str, Any]:
    global _PROBE_CACHE_LOADED
    path = _probe_cache_path()
    if not path.is_file():
        _PROBE_CACHE_LOADED = True
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    _PROBE_CACHE_LOADED = True
    return raw if isinstance(raw, dict) else {}


def _profile_from_cache_row(row: dict[str, Any], agent: AgentId, model_id: str) -> ModelProfile | None:
    if not isinstance(row, dict):
        return None
    provider = str(row.get("provider") or "local").strip().lower()
    if provider not in ("local", "openai", "anthropic"):
        provider = "local"
    return ModelProfile(
        provider=provider,  # type: ignore[arg-type]
        model_id=model_id,
        agent=agent,
        supports_tools=bool(row.get("supports_tools")),
        supports_inbox_mcp=bool(row.get("supports_inbox_mcp")),
        supports_json_envelope=bool(row.get("supports_json_envelope")),
        supports_long_context=bool(row.get("supports_long_context")),
        cost_tier=_tier(row.get("cost_tier"), "medium"),
        latency_tier=_tier(row.get("latency_tier"), "medium"),
    )


def _save_probe_cache(agent: AgentId, model_id: str, profile: ModelProfile) -> None:
    path = _probe_cache_path()
    cache: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cache = raw
        except (OSError, json.JSONDecodeError):
            cache = {}
    key = f"{agent}:{model_id.strip().lower()}"
    cache[key] = {
        "provider": profile.provider,
        "supports_tools": profile.supports_tools,
        "supports_inbox_mcp": profile.supports_inbox_mcp,
        "supports_json_envelope": profile.supports_json_envelope,
        "supports_long_context": profile.supports_long_context,
        "cost_tier": profile.cost_tier,
        "latency_tier": profile.latency_tier,
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def probe_loop_capabilities_cached(agent_id: str, model_id: str) -> ModelProfile | None:
    """Probe once per agent:model_id; reuse disk cache when probe is disabled."""
    agent = _known_agent_id(agent_id)
    if agent is None:
        agent = _substitute_agent_id(agent_id)
    if agent is None:
        return None

    mid = (model_id or resolve_runtime_model_id(agent_id)).strip()
    if not mid:
        return None

    key = f"{agent}:{mid.lower()}"
    cache = _load_probe_cache()
    cached = cache.get(key)
    if isinstance(cached, dict) and not loop_probe_enabled():
        profile = _profile_from_cache_row(cached, agent, mid)
        if profile is not None:
            register_model_profile(profile)
            return profile
    if not loop_probe_enabled():
        return None

    profile = probe_loop_capabilities(agent_id, mid)
    if profile is None:
        return None
    register_model_profile(profile)
    _save_probe_cache(agent, mid, profile)
    return profile
