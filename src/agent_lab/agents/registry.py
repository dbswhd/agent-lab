from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agent_lab.agents.plugins import (
    AGENT_IDS,
    AgentId,
    call_plugin_respond,
    get_plugin,
    label,
    plugins,
)
from agent_lab.kimi import work_provider as kimi_work_provider
from agent_lab.structured_envelope_adapter import merge_structured_reply

__all__ = [
    "AGENT_IDS",
    "AgentCallError",
    "AgentId",
    "AgentReply",
    "available_agents",
    "call_agent",
    "call_agent_reply",
    "label",
    "model_label",
    "reset_mock_act_script_cursors",
]


@dataclass(frozen=True)
class AgentReply:
    text: str
    structured_envelope: dict[str, Any] | None = None


class AgentCallError(RuntimeError):
    """Structured error from a live agent call (non-mock path)."""

    def __init__(self, agent: str, kind: str, message: str) -> None:
        self.agent = agent
        self.kind = kind
        self.message = message
        super().__init__(f"[{agent}:{kind}] {message}")


def model_label(agent: AgentId) -> str:
    return get_plugin(agent).model_label()


def available_agents() -> list[AgentId]:
    if _mock_agents_enabled():
        return list(AGENT_IDS)
    out: list[AgentId] = []
    for aid in AGENT_IDS:
        try:
            if _is_ready(aid):
                out.append(aid)
        except Exception:
            continue
    return out


def _is_ready(agent: AgentId) -> bool:
    return get_plugin(agent).is_available()


def _mock_agents_enabled() -> bool:
    return os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


_MOCK_SCRIPT_LOCK = threading.Lock()
_MOCK_SCRIPT_CURSORS: dict[tuple[str, str], int] = {}
_MOCK_SCRIPT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _load_mock_act_script(path: str) -> dict[str, Any] | None:
    import json

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    cached = _MOCK_SCRIPT_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    _MOCK_SCRIPT_CACHE[path] = (mtime, data)
    return data


def _scripted_mock_response(agent: AgentId, snippet: str) -> str | None:
    """Deterministic per-agent act sequence from AGENT_LAB_MOCK_ACT_SCRIPT (JSON path).

    Schema: {"cursor": [{"act": "PROPOSE", "refs": ["L2"], "body": "..."}, ...], ...}
    Steps are consumed in call order per agent (R1 runs in a ThreadPoolExecutor, hence
    the lock); when the sequence is exhausted the agent falls back to ENDORSE.
    """
    import json

    path = os.getenv("AGENT_LAB_MOCK_ACT_SCRIPT", "").strip()
    if not path:
        return None
    script = _load_mock_act_script(path)
    if script is None:
        return None
    steps = script.get(agent)
    if not isinstance(steps, list):
        return None
    with _MOCK_SCRIPT_LOCK:
        idx = _MOCK_SCRIPT_CURSORS.get((path, agent), 0)
        _MOCK_SCRIPT_CURSORS[(path, agent)] = idx + 1
    step = steps[idx] if idx < len(steps) and isinstance(steps[idx], dict) else {}
    act = str(step.get("act") or "ENDORSE").upper()
    env: dict[str, Any] = {
        "act": act,
        "refs": [str(r) for r in (step.get("refs") or [])],
        "confidence": float(step.get("confidence") or 0.9),
    }
    if step.get("to"):
        env["to"] = str(step["to"])
    if step.get("message"):
        env["message"] = str(step["message"])
    body = str(step.get("body") or "") or (f"[mock:{label(agent)}] {act} — {snippet or '(empty)'}")
    return f"{json.dumps(env, ensure_ascii=False)}\n{body}"


def reset_mock_act_script_cursors() -> None:
    """Test helper — restart all scripted mock sequences."""
    with _MOCK_SCRIPT_LOCK:
        _MOCK_SCRIPT_CURSORS.clear()


def _mock_agent_response(
    agent: AgentId,
    user: str,
    *,
    scribe: bool = False,
) -> str:
    if scribe:
        return "## Mock plan\n\n- mock scribe turn\n"
    snippet = " ".join(user.strip().split())[:100]
    scripted = _scripted_mock_response(agent, snippet)
    if scripted is not None:
        return scripted
    if os.getenv("AGENT_LAB_MOCK_STRUCTURED_ENVELOPE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        import json

        env = json.dumps({"act": "ENDORSE", "refs": [], "confidence": 0.9})
        return f"{env}\n[mock:{label(agent)}] ACK — {snippet or '(empty)'}"
    return f"[mock:{label(agent)}] ACK — {snippet or '(empty)'}"


def call_agent(
    agent: AgentId,
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    scribe: bool = False,
    on_activity: Callable[[str], None] | None = None,
    on_bridge_event: Callable[[str, dict[str, Any]], None] | None = None,
    session_folder: str | Path | None = None,
) -> str:
    return call_agent_reply(
        agent,
        system,
        user,
        permissions=permissions,
        scribe=scribe,
        on_activity=on_activity,
        session_folder=session_folder,
    ).text


def call_agent_reply(
    agent: AgentId,
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    scribe: bool = False,
    on_activity: Callable[[str], None] | None = None,
    on_bridge_event: Callable[[str, dict[str, Any]], None] | None = None,
    session_folder: str | Path | None = None,
    request_structured_envelope: bool = False,
    inbox_mcp: bool = False,
) -> AgentReply:
    if agent not in plugins():
        raise AgentCallError(agent, "unknown_agent", f"unknown agent: {agent}")

    if _mock_agents_enabled():
        if agent == "kimi_work" and session_folder is not None:
            if not _is_ready(agent):
                raise RuntimeError(f"{label(agent)} is not configured")
            text = kimi_work_provider.respond(
                system,
                user,
                permissions=permissions,
                on_activity=on_activity,
                on_bridge_event=on_bridge_event,
                session_folder=session_folder,
                request_structured_envelope=request_structured_envelope,
                inbox_mcp=inbox_mcp,
            )
        else:
            if on_activity:
                on_activity(f"[tool · read] src/agent_lab/{agent}/provider.py")
                on_activity("[tool · grep] mock streaming")
            text = _mock_agent_response(agent, user, scribe=scribe)
            if on_bridge_event:
                from agent_lab.room.sse_stream import chunk_text

                for chunk in chunk_text(text, chunk_size=24):
                    on_bridge_event("text", {"text": chunk})
    elif not _is_ready(agent):
        raise RuntimeError(f"{label(agent)} is not configured")
    else:
        try:
            text = call_plugin_respond(
                agent,
                system,
                user,
                permissions=permissions,
                scribe=scribe,
                on_activity=on_activity,
                on_bridge_event=on_bridge_event,
                session_folder=session_folder,
                request_structured_envelope=request_structured_envelope,
                inbox_mcp=inbox_mcp,
            )
        except AgentCallError:
            raise
        except Exception as exc:
            raise AgentCallError(agent, "call_error", str(exc)) from exc
    prose, structured = merge_structured_reply(text)
    return AgentReply(text=prose, structured_envelope=structured)
