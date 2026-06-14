"""Normalize live Cursor bridge SDK stream events for Room SSE."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_lab.cursor_activity import (
    activity_from_tool_call,
    format_conversation_step,
    format_interaction_update,
)
from agent_lab.room_sse_stream import chunk_text, format_tool_activity_line

StreamEvent = tuple[str, dict[str, Any]]


def _update_type(update: Any) -> str | None:
    utype = getattr(update, "type", None)
    if utype is None and isinstance(update, Mapping):
        utype = update.get("type")
    return str(utype) if utype else None


def _tool_payload(tool_call: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    name = str(tool_call.get("name") or tool_call.get("toolName") or "tool").strip()
    args = tool_call.get("args") or tool_call.get("arguments") or {}
    if not isinstance(args, Mapping):
        args = {}
    target = ""
    for key in ("path", "file", "command", "target", "query"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            target = val.strip()
            break
    return name or "tool", {"target": target} if target else {}


def _shell_output_chunk(event: Mapping[str, Any]) -> str:
    for key in ("stdout", "output", "text", "data", "chunk"):
        val = event.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def parse_interaction_update(update: Any) -> list[StreamEvent]:
    """Map Cursor SDK ``on_delta`` updates to Room stream events."""
    utype = _update_type(update)
    if utype == "text-delta":
        text = str(getattr(update, "text", "") or "").strip("\x00")
        if not text:
            return []
        return [("text", {"text": text})]

    if utype == "token-delta":
        return []

    if utype == "tool-call-started":
        tool_call = getattr(update, "tool_call", None) or {}
        if not isinstance(tool_call, Mapping):
            return []
        tool, args = _tool_payload(tool_call)
        events: list[StreamEvent] = [
            ("tool_start", {"tool": tool, "args": args}),
        ]
        label = activity_from_tool_call(tool_call)
        if label:
            events.append(
                ("activity", {"text": format_tool_activity_line(tool=tool, args=args.get("target", "")) or label})
            )
        return events

    if utype == "tool-call-completed":
        tool_call = getattr(update, "tool_call", None) or {}
        if not isinstance(tool_call, Mapping):
            return []
        tool, args = _tool_payload(tool_call)
        detail = str(tool_call.get("result") or tool_call.get("output") or "").strip()
        events = [("tool_done", {"tool": tool})]
        if detail:
            events.insert(0, ("tool_output", {"tool": tool, "chunk": detail[:500]}))
        return events

    if utype == "shell-output-delta":
        event = getattr(update, "event", None) or {}
        if not isinstance(event, Mapping):
            return []
        chunk = _shell_output_chunk(event)
        if not chunk:
            return []
        return [
            ("tool_output", {"tool": "shell", "chunk": chunk}),
            ("activity", {"text": format_tool_activity_line(tool="shell", args=chunk[:120])}),
        ]

    label = format_interaction_update(update)
    if label:
        return [("activity", {"text": label})]
    return []


def parse_conversation_step(step: Any) -> list[StreamEvent]:
    """Map Cursor SDK ``on_step`` events to Room stream events."""
    label = format_conversation_step(step)
    if not label:
        return []
    stype = _update_type(step)
    if stype == "toolCall":
        msg = getattr(step, "message", None) or {}
        if isinstance(msg, Mapping):
            tool, args = _tool_payload(msg)
            return [
                ("tool_start", {"tool": tool, "args": args}),
                ("activity", {"text": format_tool_activity_line(tool=tool, args=args.get("target", "")) or label}),
            ]
    return [("activity", {"text": label})]


def parse_stream_update(update: Any, *, from_step: bool = False) -> list[StreamEvent]:
    if from_step:
        return parse_conversation_step(update)
    return parse_interaction_update(update)


def _codex_agent_message(item: Mapping[str, Any]) -> str | None:
    if item.get("type") != "agent_message":
        return None
    for key in ("text", "content", "message"):
        raw = item.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def parse_codex_json_event(event: Mapping[str, Any]) -> list[StreamEvent]:
    """Map Codex CLI ``--json`` JSONL events to Room bridge stream events."""
    from agent_lab.codex_cli import codex_event_label

    typ = event.get("type")
    item = event.get("item") if isinstance(event.get("item"), Mapping) else {}
    item_type = item.get("type")

    if typ == "item.started" and item_type == "command_execution":
        cmd = str(item.get("command") or "").strip()
        target = cmd[:120] if cmd else ""
        events: list[StreamEvent] = [
            ("tool_start", {"tool": "shell", "args": {"target": target} if target else {}}),
        ]
        line = format_tool_activity_line(tool="shell", args=target) if target else "shell 실행 중"
        events.append(("activity", {"text": line}))
        return events

    if typ == "item.completed" and item_type == "command_execution":
        code = item.get("exit_code")
        events = [("tool_done", {"tool": "shell"})]
        if code not in (None, 0):
            events.insert(
                0,
                ("tool_output", {"tool": "shell", "chunk": f"exit {code}"}),
            )
        return events

    if typ == "item.completed" and item_type == "agent_message":
        msg = _codex_agent_message(item)
        if not msg:
            return []
        return [("text", {"text": chunk}) for chunk in chunk_text(msg, chunk_size=32)]

    label = codex_event_label(dict(event))
    if label:
        return [("activity", {"text": label})]
    return []


def _claude_tool_target(inp: Mapping[str, Any]) -> str:
    for key in ("file_path", "path", "command", "pattern", "query"):
        val = inp.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:120]
    return ""


def _claude_content_blocks(message: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    content = message.get("content")
    if isinstance(content, list):
        return [b for b in content if isinstance(b, Mapping)]
    return []


def parse_claude_json_event(event: Mapping[str, Any]) -> list[StreamEvent]:
    """Map Claude CLI ``--output-format stream-json`` NDJSON to Room bridge events."""
    typ = event.get("type")

    if typ == "stream_event":
        inner = event.get("event") if isinstance(event.get("event"), Mapping) else {}
        delta = inner.get("delta") if isinstance(inner.get("delta"), Mapping) else {}
        if delta.get("type") == "text_delta":
            text = str(delta.get("text") or "")
            if text:
                return [("text", {"text": text})]
        return []

    if typ == "assistant":
        message = event.get("message") if isinstance(event.get("message"), Mapping) else {}
        events: list[StreamEvent] = []
        for block in _claude_content_blocks(message):
            if block.get("type") != "tool_use":
                continue
            tool = str(block.get("name") or "tool")
            inp = block.get("input") if isinstance(block.get("input"), Mapping) else {}
            target = _claude_tool_target(inp)
            events.append(
                ("tool_start", {"tool": tool, "args": {"target": target} if target else {}}),
            )
            line = format_tool_activity_line(tool=tool, args=target) or f"[tool · {tool}]"
            events.append(("activity", {"text": line}))
        return events

    if typ == "user":
        message = event.get("message") if isinstance(event.get("message"), Mapping) else {}
        for block in _claude_content_blocks(message):
            if block.get("type") != "tool_result":
                continue
            raw = block.get("content")
            chunk = ""
            if isinstance(raw, str):
                chunk = raw[:500]
            elif isinstance(raw, list):
                chunk = str(raw)[:500]
            tool = str(block.get("name") or "tool")
            out: list[StreamEvent] = []
            if chunk:
                out.append(("tool_output", {"tool": tool, "chunk": chunk}))
            out.append(("tool_done", {"tool": tool}))
            return out
        return []

    if typ == "result":
        return []

    subtype = event.get("subtype")
    if typ == "system" and subtype == "init":
        return []
    return []
