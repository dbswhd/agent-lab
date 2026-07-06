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
                reasoning_parts.append(raw.lstrip("\n\r\t"))
                break
    return reasoning_parts


def _merge_reasoning_parts(parts: list[str]) -> str:
    """Merge reasoning parts — cumulative last wins, else concatenate deltas."""
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    merged = parts[0]
    for piece in parts[1:]:
        if not piece:
            continue
        if piece.startswith(merged):
            merged = piece
        elif merged.startswith(piece):
            continue
        elif piece in merged:
            continue
        else:
            if (
                merged
                and piece
                and not merged.endswith((" ", "\n"))
                and not piece.startswith((" ", "\n", "/", ".", ",", ":", ";", ")", "]", "}"))
            ):
                merged += " "
            merged += piece
    return merged


def _merge_visible_text_parts(parts: list[str]) -> str:
    """Merge visible text parts — handles stacked cumulative snapshots safely."""
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    from agent_lab.room.sse_stream import CumulativeTextStreamer

    streamer = CumulativeTextStreamer()
    for piece in parts:
        if piece:
            streamer.feed(piece)
    return streamer.body


def assistant_reasoning_text(payload: dict[str, Any]) -> str:
    """Chain-of-thought while no visible ``kind: text`` part exists yet."""
    if _visible_text_parts(payload):
        return ""
    reasoning_parts = _reasoning_text_parts(payload)
    if reasoning_parts:
        return _merge_reasoning_parts(reasoning_parts)
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


def thinking_activity_delta(
    previous_flat: str,
    cumulative: str,
    *,
    tail: int = 72,
) -> str:
    """Emit only newly grown reasoning text (avoids overlapping tail spam)."""
    flat = " ".join(cumulative.strip().split())
    prev = " ".join(previous_flat.strip().split())
    if not flat or flat == prev:
        return ""
    if flat.startswith(prev):
        delta = flat[len(prev) :].strip()
    else:
        # Provider resync — show the latest tail only.
        delta = flat[-tail:] if len(flat) > tail else flat
        if delta and not delta.startswith("…"):
            delta = f"…{delta}" if len(flat) > tail else delta
    if not delta:
        return ""
    if len(delta) > tail:
        delta = f"…{delta[-tail:]}"
    return f"[thinking] {delta}"


def assistant_reply_text(payload: dict[str, Any]) -> str:
    """Extract visible assistant reply text (``kind: text``; skips reasoning/tools)."""
    parts = push_message_parts(payload)
    text_parts = _visible_text_parts(payload)
    if text_parts:
        return _merge_visible_text_parts(text_parts)
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
