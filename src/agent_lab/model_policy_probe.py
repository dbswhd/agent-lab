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
    from agent_lab.workspace.roots import project_root

    override = (os.getenv("AGENT_LAB_LOOP_PROBE_CACHE") or "").strip()
    if override:
        return Path(override).expanduser()
    return project_root() / ".agent-lab" / "loop_probe_cache.json"


def _mock_mode() -> bool:
    return os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {"1", "true", "yes", "on"}


def _probe_session_folder(agent: AgentId) -> Path:
    from agent_lab.workspace.roots import project_root

    folder = project_root() / ".agent-lab" / "loop-probe-sessions" / agent
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _prepare_kimi_work_probe_session(folder: Path) -> bool:
    """Bind a live daimon conversation for loop envelope probe; no-op in mock mode."""
    if _mock_mode():
        return True
    from agent_lab.kimi.work_provider import is_configured
    from agent_lab.kimi.work_session import (
        clear_conversation_key,
        ensure_kimi_work_session,
        get_conversation_key,
        is_usable_conversation_key,
    )
    from agent_lab.workspace.roots import project_root

    if not is_configured():
        return False
    key = get_conversation_key(folder)
    if key and not is_usable_conversation_key(key):
        clear_conversation_key(folder)
    try:
        ensure_kimi_work_session(
            folder,
            workspace_path=project_root(),
            title="loop-probe",
        )
    except Exception:
        return False
    return is_usable_conversation_key(get_conversation_key(folder))


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


def _probe_kimi_work_tools() -> bool:
    if _mock_mode():
        return True
    from agent_lab.kimi.control_client import probe_control, rpc
    from agent_lab.kimi.work_loop import kimi_work_loop_tool_features_ok
    from agent_lab.kimi.work_provider import is_configured

    if not is_configured():
        return False
    bridge, _err = probe_control()
    if bridge != "ok":
        return False
    try:
        caps = rpc("capabilities.get", {})
        features = caps.get("features") if isinstance(caps, dict) else None
        return kimi_work_loop_tool_features_ok(features)
    except Exception:
        return False


def _probe_kimi_work_inbox() -> bool:
    from agent_lab.kimi.work_inbox_bridge import kimi_work_inbox_bridge_ready
    from agent_lab.kimi.work_loop import kimi_work_loop_inbox_features_ok, kimi_work_loop_phase

    if kimi_work_loop_phase() < 2:
        return False
    if not kimi_work_inbox_bridge_ready():
        return False
    if _mock_mode():
        return True
    from agent_lab.kimi.control_client import probe_control, rpc
    from agent_lab.kimi.work_provider import is_configured

    if not is_configured():
        return False
    bridge, _err = probe_control()
    if bridge != "ok":
        return False
    try:
        caps = rpc("capabilities.get", {})
        features = caps.get("features") if isinstance(caps, dict) else None
        if isinstance(features, list) and kimi_work_loop_inbox_features_ok(features):
            return True
    except Exception:
        pass
    # Agent Lab-side bridge is sufficient for Loop phase 2 even before daimon advertises inbox.*.
    return True


def _envelope_reply_valid(reply: Any) -> bool:
    """True when reply parses to a valid Loop consensus speech act."""
    from agent_lab.agent.envelope import VALID_ACTS, parse_agent_response_v2

    structured = getattr(reply, "structured_envelope", None)
    parsed = parse_agent_response_v2(reply.text, structured=structured)
    if parsed.envelope is not None:
        act = str(parsed.envelope.act or "").strip()
        return act in VALID_ACTS
    try:
        first = reply.text.strip().splitlines()[0].strip()
        data = json.loads(first)
    except (IndexError, json.JSONDecodeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    act = str(data.get("act") or "").strip()
    return act in VALID_ACTS


def _probe_substitute_envelope(agent: AgentId, model_id: str) -> bool:
    """Verify structured speech-act output (Loop consensus lane)."""
    from agent_lab.agents import registry
    from agent_lab.loop_probe_eval import _LOOP_EVAL_SYSTEM, _LOOP_EVAL_USER

    if not registry._is_ready(agent):
        return False

    folder: Path | None = None
    if agent == "kimi_work":
        folder = _probe_session_folder(agent)
        if not _prepare_kimi_work_probe_session(folder):
            return False
    try:
        reply = registry.call_agent_reply(
            agent,
            system=_LOOP_EVAL_SYSTEM,
            user=_LOOP_EVAL_USER,
            request_structured_envelope=True,
            session_folder=folder,
        )
    except Exception:
        return False

    return _envelope_reply_valid(reply)


def _probe_substitute_loop_flags(agent: AgentId, model_id: str) -> tuple[bool, bool, bool]:
    """Return (supports_tools, supports_inbox_mcp, supports_json_envelope) for substitutes."""
    if agent == "kimi_work":
        tools = _probe_kimi_work_tools()
        envelope = _probe_substitute_envelope(agent, model_id) if tools else False
        inbox = _probe_kimi_work_inbox()
        return tools, inbox, envelope

    if _mock_mode():
        return True, True, True
    live_ok = _probe_substitute_envelope(agent, model_id)
    if live_ok:
        return True, True, True
    return False, False, False


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

    # Stage-2: per-capability probe for substitutes; built-ins only when live flag on.
    if agent in ("kimi", "kimi_work", "local"):
        tools, inbox, envelope = _probe_substitute_loop_flags(agent, mid)
        profile = replace(
            profile,
            supports_tools=tools,
            supports_inbox_mcp=inbox,
            supports_json_envelope=envelope,
        )
    elif _live_probe_enabled() and not _probe_substitute_envelope(agent, mid):
        profile = replace(
            profile,
            supports_tools=False,
            supports_inbox_mcp=False,
            supports_json_envelope=False,
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
