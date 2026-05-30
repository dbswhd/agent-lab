"""Map Cursor SDK stream events to short activity lines (Thought / Explored / Edited)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def _short(text: str, limit: int = 52) -> str:
    one = " ".join(text.split())
    if len(one) <= limit:
        return one
    return f"{one[: limit - 1]}…"


def _extract_path(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return ""
    for key in ("path", "file", "filePath", "file_path", "targetPath", "target"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _tool_kind_and_payload(tool_call: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    name = str(tool_call.get("name") or tool_call.get("toolName") or "").lower()
    args = tool_call.get("args") or tool_call.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, Mapping):
        args = {}

    if name:
        return name, args

    for key, val in tool_call.items():
        if key in ("name", "toolName", "args", "arguments", "callId", "call_id"):
            continue
        if isinstance(val, Mapping):
            return str(key).lower(), val
    return "", args


def activity_from_tool_call(tool_call: Mapping[str, Any]) -> str | None:
    kind, payload = _tool_kind_and_payload(tool_call)
    path = _extract_path(payload)
    k = kind.lower()

    if any(x in k for x in ("read", "grep", "glob", "search", "list", "ls", "semantic")):
        return f"Explored {_short(path)}" if path else "Explored…"
    if any(x in k for x in ("edit", "write", "strreplace", "apply", "patch", "replace")):
        return f"Edited {_short(path)}" if path else "Edited…"
    if any(x in k for x in ("shell", "terminal", "bash", "command")):
        cmd = payload.get("command") if isinstance(payload, Mapping) else ""
        if isinstance(cmd, str) and cmd.strip():
            return f"Ran {_short(cmd, 40)}"
        return "Ran command"
    if "mcp" in k:
        return "Used tool"
    if kind:
        label = kind.replace("ToolCall", "").replace("tool", "").strip() or kind
        return _short(label, 40)
    return None


def activity_from_thinking_completed(duration_ms: int) -> str:
    if duration_ms <= 0:
        return "Thought briefly"
    if duration_ms < 4000:
        return "Thought briefly"
    secs = max(1, round(duration_ms / 1000))
    return f"Thought for {secs}s"


def format_interaction_update(update: Any) -> str | None:
    """Return a one-line activity label, or None to skip."""
    utype = getattr(update, "type", None) or (
        update.get("type") if isinstance(update, Mapping) else None
    )
    if utype == "thinking-completed":
        ms = int(getattr(update, "thinking_duration_ms", 0) or 0)
        return activity_from_thinking_completed(ms)
    if utype == "tool-call-started":
        tool_call = getattr(update, "tool_call", None) or {}
        if isinstance(tool_call, Mapping):
            return activity_from_tool_call(tool_call)
    if utype == "summary":
        summary = str(getattr(update, "summary", "") or "").strip()
        return _short(summary) if summary else None
    if utype == "summary-started":
        return None
    return None


def format_conversation_step(step: Any) -> str | None:
    stype = getattr(step, "type", None) or (
        step.get("type") if isinstance(step, Mapping) else None
    )
    if stype == "thinkingMessage":
        msg = getattr(step, "message", None)
        text = str(getattr(msg, "text", "") or "").strip()
        if text:
            return _short(text, 56)
        ms = getattr(msg, "thinking_duration_ms", None)
        if isinstance(ms, int):
            return activity_from_thinking_completed(ms)
        return "Thought briefly"
    if stype == "toolCall":
        msg = getattr(step, "message", None)
        if isinstance(msg, Mapping):
            return activity_from_tool_call(msg)
    return None
