from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_lab.agent.envelope import AgentEnvelope, parse_agent_response
from agent_lab.env_flags import env_bool
from agent_lab.model_policy import (
    AgentId,
    ModelProfile,
    _known_agent_id,
    _loop_eval_registry_path,
    _tier,
    agent_model_profiles,
    load_loop_eval_registry,
    register_model_profile,
    resolve_runtime_model_id,
)
from agent_lab.model_policy_probe import probe_loop_capabilities

EvalSource = Literal["static", "mock", "live"]

_LOOP_EVAL_SYSTEM = (
    "Loop readiness eval. Reply with exactly one ```agent-envelope fenced JSON block "
    "and optional short body after the fence."
)
_LOOP_EVAL_USER = (
    "Respond with ONLY this structure (no preamble):\n"
    "```agent-envelope\n"
    '{"act":"ENDORSE","refs":[],"confidence":0.9}\n'
    "```\n"
    "Loop eval probe."
)


def _mock_agents_enabled() -> bool:
    return env_bool("AGENT_LAB_MOCK_AGENTS")


def _eval_source() -> EvalSource:
    if _mock_agents_enabled():
        return "mock"
    return "live"


def _reply_has_envelope(text: str) -> bool:
    parsed = parse_agent_response(text)
    if parsed.envelope is not None:
        return True
    first_line = (text or "").strip().split("\n", 1)[0].strip()
    if not first_line:
        return False
    try:
        data = json.loads(first_line)
    except json.JSONDecodeError:
        return False
    return AgentEnvelope.from_dict(data) is not None


def eval_loop_profile_row(
    agent_id: str,
    model_id: str | None = None,
    *,
    static_only: bool = False,
) -> dict[str, Any] | None:
    """Evaluate loop capabilities for one agent model (static, mock, or live)."""
    agent = _known_agent_id(agent_id)
    if agent is None:
        return None
    mid = (model_id or resolve_runtime_model_id(agent_id)).strip()
    if not mid:
        return None

    static = probe_loop_capabilities(agent_id, mid)
    if static is None:
        return None

    source: EvalSource = "static"
    eval_error: str | None = None
    supports_tools = static.supports_tools
    supports_inbox = static.supports_inbox_mcp
    supports_envelope = static.supports_json_envelope

    if not static_only:
        source = _eval_source()
        if source in ("mock", "live"):
            try:
                from agent_lab.agents.registry import call_agent_reply

                reply = call_agent_reply(
                    agent,
                    _LOOP_EVAL_SYSTEM,
                    _LOOP_EVAL_USER,
                    request_structured_envelope=True,
                    inbox_mcp=True,
                )
                supports_tools = True
                supports_envelope = _reply_has_envelope(reply.text)
                if reply.structured_envelope:
                    supports_envelope = True
            except Exception as exc:
                eval_error = str(exc)
                supports_tools = False
                supports_envelope = False

    return {
        "agent": agent,
        "model_id": mid,
        "provider": static.provider,
        "supports_tools": supports_tools,
        "supports_inbox_mcp": supports_inbox,
        "supports_json_envelope": supports_envelope,
        "supports_long_context": static.supports_long_context,
        "cost_tier": static.cost_tier,
        "latency_tier": static.latency_tier,
        "eval_source": source,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "eval_error": eval_error,
    }


def profile_from_eval_row(row: dict[str, Any]) -> ModelProfile | None:
    agent = _known_agent_id(str(row.get("agent") or ""))
    model_id = str(row.get("model_id") or "").strip()
    if agent is None or not model_id:
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


def write_loop_eval_registry(
    profiles: list[dict[str, Any]],
    path: Path | None = None,
) -> Path:
    target = path or _loop_eval_registry_path()
    payload = {
        "profiles": profiles,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def apply_eval_rows_to_registry(rows: list[dict[str, Any]]) -> int:
    applied = 0
    for row in rows:
        profile = profile_from_eval_row(row)
        if profile is None:
            continue
        register_model_profile(profile)
        applied += 1
    return applied


def default_eval_agent_ids() -> list[AgentId]:
    return list(agent_model_profiles().keys())


def run_loop_model_eval(
    agent_ids: list[str] | None = None,
    *,
    static_only: bool = False,
    write_registry: bool = True,
    registry_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Run loop eval for configured agents and optionally persist loop_model_eval.json."""
    ids = agent_ids or default_eval_agent_ids()
    rows: list[dict[str, Any]] = []
    for raw_id in ids:
        row = eval_loop_profile_row(raw_id, static_only=static_only)
        if row is not None:
            rows.append(row)
    if write_registry and rows:
        write_loop_eval_registry(rows, registry_path)
        load_loop_eval_registry(force=True)
    return rows
