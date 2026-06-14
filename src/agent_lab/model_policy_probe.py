from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.model_policy import (
    AgentId,
    ModelProfile,
    ProviderId,
    Tier,
    _known_agent_id,
    _tier,
    register_model_profile,
    resolve_runtime_model_id,
)

_PROBE_CACHE_LOADED = False


def loop_probe_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_LOOP_PROBE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


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


def probe_loop_capabilities(agent_id: str, model_id: str) -> ModelProfile | None:
    """Static runtime probe (no LLM): agent bridge + inbox + envelope infrastructure."""
    agent = _known_agent_id(agent_id)
    if agent is None:
        return None
    mid = (model_id or resolve_runtime_model_id(agent_id)).strip()
    if not mid:
        return None
    provider: ProviderId = "local" if agent == "cursor" else ("openai" if agent == "codex" else "anthropic")
    supports_tools = _probe_supports_tools(agent)
    supports_inbox = _probe_supports_inbox_mcp(agent)
    supports_envelope = _probe_supports_json_envelope(agent)
    cost: Tier = "low" if provider == "local" else "high"
    return ModelProfile(
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
        provider=provider,
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
