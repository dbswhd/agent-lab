"""Map Kimi Work daimon WS push payloads to Room bridge events."""

from __future__ import annotations

import json
from typing import Any, Callable

from agent_lab.kimi_work_push_payload import (
    assistant_reasoning_text,
    assistant_reply_text,
    push_message_parts,
    thinking_activity_delta,
)
from agent_lab.room_sse_stream import CumulativeTextStreamer

BridgeEmit = Callable[[str, dict[str, Any]], None]

_THINKING_EMIT_MIN_CHARS = 48


def _tool_name(part: dict[str, Any]) -> str:
    for key in ("toolName", "name"):
        val = part.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    call_id = part.get("toolCallId")
    return str(call_id).strip() if call_id else "tool"


def _tool_args(part: dict[str, Any]) -> dict[str, Any]:
    raw = part.get("args")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"raw": raw}
    return {}


class KimiWorkPushMapper:
    """Stateful mapper — snapshots are cumulative; dedupe tool_start per toolCallId."""

    def __init__(self) -> None:
        self._started: set[str] = set()
        self._result_lens: dict[str, int] = {}
        self._done: set[str] = set()
        self._reply_stream = CumulativeTextStreamer()
        self._reasoning_stream = CumulativeTextStreamer()
        self._last_thinking_flat = ""

    def reset(self) -> None:
        self._started.clear()
        self._result_lens.clear()
        self._done.clear()
        self._reply_stream.reset()
        self._reasoning_stream.reset()
        self._last_thinking_flat = ""

    def emit_push(
        self,
        method: str,
        payload: dict[str, Any],
        on_bridge_event: BridgeEmit | None,
    ) -> None:
        if on_bridge_event is None:
            return
        if method == "conversations.message.snapshot":
            self._emit_snapshot(payload, on_bridge_event)
            return
        if method == "conversations.message.complete":
            text = assistant_reply_text(payload)
            if text:
                for delta in self._reply_stream.feed(text):
                    if delta:
                        on_bridge_event("text", {"text": delta})
            return
        if method == "conversations.message.cancelled":
            reason = str(payload.get("message") or payload.get("reason") or "turn cancelled")
            on_bridge_event("activity", {"text": f"[system] {reason}"})
            return

    def _emit_snapshot(self, payload: dict[str, Any], on_bridge_event: BridgeEmit) -> None:
        parts = push_message_parts(payload)
        if parts:
            self._emit_parts(parts, on_bridge_event)
        text = assistant_reply_text(payload)
        if text:
            for delta in self._reply_stream.feed(text):
                if delta:
                    on_bridge_event("text", {"text": delta})
            return
        self._emit_reasoning_activity(payload, on_bridge_event)

    def _emit_reasoning_activity(self, payload: dict[str, Any], on_bridge_event: BridgeEmit) -> None:
        raw = assistant_reasoning_text(payload)
        if not raw:
            return
        grew = False
        for delta in self._reasoning_stream.feed(raw):
            if delta:
                grew = True
        if not grew:
            return
        cumulative = self._reasoning_stream.body
        flat = " ".join(cumulative.strip().split())
        if not flat or flat == self._last_thinking_flat:
            return
        growth = len(flat) - len(self._last_thinking_flat)
        if self._last_thinking_flat and growth < _THINKING_EMIT_MIN_CHARS:
            return
        line = thinking_activity_delta(self._last_thinking_flat, cumulative)
        if not line:
            return
        self._last_thinking_flat = flat
        on_bridge_event("activity", {"text": line})

    def _emit_parts(self, parts: list[Any], on_bridge_event: BridgeEmit) -> None:
        for item in parts:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or item.get("type") or "").strip()
            if kind == "tool-call":
                call_id = str(item.get("toolCallId") or _tool_name(item))
                if call_id not in self._started:
                    self._started.add(call_id)
                    on_bridge_event(
                        "tool_start",
                        {"tool": _tool_name(item), "args": _tool_args(item)},
                    )
                continue
            if kind == "tool-result":
                call_id = str(item.get("toolCallId") or _tool_name(item))
                tool = _tool_name(item)
                result = item.get("result")
                if result is None:
                    result = item.get("delta")
                chunk = ""
                if isinstance(result, str):
                    chunk = result
                elif result is not None:
                    chunk = json.dumps(result, ensure_ascii=False)
                prev = self._result_lens.get(call_id, 0)
                if chunk and len(chunk) > prev:
                    delta = chunk[prev:]
                    self._result_lens[call_id] = len(chunk)
                    if delta:
                        on_bridge_event("tool_output", {"tool": tool, "chunk": delta})
                if item.get("status") in {"succeeded", "done", "complete"} or result is not None:
                    if call_id not in self._done:
                        self._done.add(call_id)
                        on_bridge_event("tool_done", {"tool": tool})
                continue
            if kind in {"tool-start", "tool_start"}:
                call_id = str(item.get("toolCallId") or _tool_name(item))
                if call_id not in self._started:
                    self._started.add(call_id)
                    on_bridge_event(
                        "tool_start",
                        {"tool": _tool_name(item), "args": _tool_args(item)},
                    )
