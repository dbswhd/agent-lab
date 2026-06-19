"""Normalize Kimi Work daimon push payloads (fixture + live shapes)."""

from __future__ import annotations

from typing import Any

_TOOL_PART_KINDS = frozenset(
    {
        "tool-call",
        "tool_call",
        "tool-result",
        "tool_result",
        "tool-start",
        "tool_start",
    },
)


def push_message_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return message parts from top-level or nested ``message.parts`` (live daimon)."""
    parts = payload.get("parts")
    if isinstance(parts, list):
        return [p for p in parts if isinstance(p, dict)]
    message = payload.get("message")
    if isinstance(message, dict):
        nested = message.get("parts")
        if isinstance(nested, list):
            return [p for p in nested if isinstance(p, dict)]
    return []


def _visible_text_parts(payload: dict[str, Any]) -> list[str]:
    text_parts: list[str] = []
    for item in push_message_parts(payload):
        kind = str(item.get("kind") or item.get("type") or "").strip().lower()
        if kind in _TOOL_PART_KINDS or kind.startswith("tool-") or kind == "reasoning":
            continue
        if kind not in {"", "text", "assistant", "markdown", "content"}:
            continue
        piece = ""
        for key in ("text", "content", "delta", "markdown"):
            raw = item.get(key)
            if isinstance(raw, str) and raw.strip():
                piece = raw
                break
        if piece:
            text_parts.append(piece)
    return text_parts


def _reasoning_text_parts(payload: dict[str, Any]) -> list[str]:
    reasoning_parts: list[str] = []
    for item in push_message_parts(payload):
        kind = str(item.get("kind") or item.get("type") or "").strip().lower()
        if kind != "reasoning":
            continue
        for key in ("text", "content", "delta", "markdown"):
            raw = item.get(key)
            if isinstance(raw, str) and raw.strip():
                reasoning_parts.append(raw.strip())
                break
    return reasoning_parts


def assistant_reasoning_text(payload: dict[str, Any]) -> str:
    """Chain-of-thought while no visible ``kind: text`` part exists yet."""
    if _visible_text_parts(payload):
        return ""
    reasoning_parts = _reasoning_text_parts(payload)
    if reasoning_parts:
        return reasoning_parts[-1]
    parts = push_message_parts(payload)
    if not parts:
        return ""
    text = str(payload.get("text") or "").strip()
    if text:
        return text
    message = payload.get("message")
    if isinstance(message, dict):
        for key in ("text", "content"):
            nested = str(message.get(key) or "").strip()
            if nested:
                return nested
    return ""


def thinking_activity_line(cumulative: str, *, tail: int = 96) -> str:
    """One-line thinking preview for the activity log (not the reply body)."""
    flat = " ".join(cumulative.strip().split())
    if not flat:
        return ""
    if len(flat) <= tail:
        return f"[thinking] {flat}"
    return f"[thinking] …{flat[-tail:]}"


def assistant_reply_text(payload: dict[str, Any]) -> str:
    """Extract visible assistant reply text (``kind: text``; skips reasoning/tools)."""
    parts = push_message_parts(payload)
    text_parts = _visible_text_parts(payload)
    if text_parts:
        return text_parts[-1]
    # When live daimon sends ``parts`` (incl. reasoning), ignore top-level ``text`` /
    # ``message.text`` — those fields often carry chain-of-thought, not the final reply.
    if parts:
        return ""
    text = str(payload.get("text") or "").strip()
    if text:
        return text
    message = payload.get("message")
    if isinstance(message, dict):
        for key in ("text", "content"):
            nested = str(message.get(key) or "").strip()
            if nested:
                return nested
    return ""
