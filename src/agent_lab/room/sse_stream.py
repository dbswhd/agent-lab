from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

EmitFn = Callable[[str, dict[str, Any]], None]

_TOOL_LINE_RE = re.compile(
    r"^\[tool · (?P<tool>[^\]]+)\]\s*(?P<args>.*)$",
    re.IGNORECASE,
)

_CLI_TOOL_PREFIXES: tuple[tuple[str, str], ...] = (
    ("Read ", "read"),
    ("Grep ", "grep"),
    ("Bash", "bash"),
    ("Edit ", "edit"),
    ("Write ", "write"),
    ("Shell ", "shell"),
)


def chunk_text(text: str, *, chunk_size: int = 32) -> list[str]:
    if not text:
        return []
    if chunk_size < 1:
        chunk_size = 32
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _longest_common_prefix(a: str, b: str) -> int:
    limit = min(len(a), len(b))
    i = 0
    while i < limit and a[i] == b[i]:
        i += 1
    return i


def _longest_common_suffix(a: str, b: str) -> int:
    limit = min(len(a), len(b))
    i = 0
    while i < limit and a[-1 - i] == b[-1 - i]:
        i += 1
    return i


# Below this, a matching tail is treated as coincidental rather than a
# genuinely stable trailing block (e.g. a finished reply body).
_RESYNC_SUFFIX_MIN_CHARS = 24


class CumulativeTextStreamer:
    """Emit only new suffixes when providers send cumulative snapshots."""

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, text: str) -> list[str]:
        if not text:
            return []
        if not self._buffer:
            self._buffer = text
            return [text]
        if text == self._buffer:
            return []
        if text.startswith(self._buffer):
            delta = text[len(self._buffer) :]
            self._buffer = text
            return [delta] if delta else []
        if self._buffer.startswith(text) and len(text) > 1:
            return []
        # Longer cumulative snapshot that lost prefix alignment — resync via LCP.
        if len(text) > len(self._buffer):
            prefix_overlap = _longest_common_prefix(self._buffer, text)
            shorter = min(len(self._buffer), len(text))
            suffix_overlap = min(
                _longest_common_suffix(self._buffer, text),
                max(shorter - prefix_overlap, 0),
            )
            if suffix_overlap >= _RESYNC_SUFFIX_MIN_CHARS and suffix_overlap >= prefix_overlap:
                # A stable trailing block (e.g. a finished reply body) is
                # being re-sent behind a still-revising leading segment
                # (e.g. an in-progress envelope header). Consumers only
                # append deltas, so re-emitting that tail would duplicate
                # it every time the leading segment changes.
                self._buffer = text
                return []
            if prefix_overlap > 0:
                delta = text[prefix_overlap:]
                self._buffer = text
                return [delta] if delta else []
            self._buffer += text
            return [text]
        # Shorter incremental tail (e.g. cursor mock slices).
        self._buffer += text
        return [text]

    @property
    def body(self) -> str:
        return self._buffer

    def reset(self) -> None:
        self._buffer = ""



# Below this, a matching tail block is treated as coincidental short-phrase
# repetition rather than a genuinely re-emitted answer.
_TAIL_DUPE_MIN_CHARS = 150


def _dedupe_repeated_tail_block(t: str) -> str:
    """Drop a substantial tail of ``t`` that exactly duplicates an earlier
    block in the same text (e.g. a cumulative-snapshot provider like Cursor
    re-emitting its full completed answer after a stream resync glitch —
    see ``CumulativeTextStreamer``'s fallback branches, which can append a
    whole new snapshot instead of diffing it against the buffer). Only
    catches an *exact*, substantial repeat; distinct surrounding narration
    on each side is left untouched."""
    n = len(t)
    if n < _TAIL_DUPE_MIN_CHARS * 2:
        return t
    for k in range(n // 2, _TAIL_DUPE_MIN_CHARS - 1, -1):
        tail = t[n - k :]
        idx = t.find(tail)
        if idx != -1 and idx < n - k:
            return t[: idx + k].rstrip()
    return t


def dedupe_adjacent_stream_dupes(text: str) -> str:
    """Drop back-to-back repeated paragraphs and exact halved duplicates."""
    t = text.strip()
    if not t:
        return text
    half = len(t) // 2
    if len(t) % 2 == 0 and half > 0 and t[:half] == t[half:]:
        return t[:half]
    t = _dedupe_repeated_tail_block(t)
    parts = re.split(r"\n{2,}", t)
    if len(parts) < 2:
        return t
    out: list[str] = []
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        if out and out[-1].strip() == chunk:
            continue
        out.append(part)
    return "\n\n".join(out)


def choose_agent_reply_body(
    *,
    streamed: str,
    final_body: str,
) -> str:
    """Pick the most complete agent reply for persist/UI (not length-only)."""
    streamed_clean = dedupe_adjacent_stream_dupes(streamed)
    final_clean = dedupe_adjacent_stream_dupes(final_body)
    if not streamed_clean.strip():
        return final_clean or final_body
    if not final_clean.strip():
        return streamed_clean
    if final_clean.startswith(streamed_clean):
        return final_clean
    if streamed_clean.startswith(final_clean) and len(streamed_clean) > len(final_clean) + 40:
        return streamed_clean
    # Claude CLI ``result`` is often only the last assistant line after tool loops.
    if len(final_clean) < max(200, len(streamed_clean) // 8):
        return streamed_clean
    if len(final_clean) >= len(streamed_clean):
        return final_clean
    return streamed_clean


def emit_agent_tokens(
    emit: EmitFn,
    *,
    agent: str,
    round: int,
    text: str,
    chunk_size: int = 32,
) -> None:
    for chunk in chunk_text(text, chunk_size=chunk_size):
        emit(
            "agent_token",
            {"agent": agent, "round": round, "text": chunk},
        )


def format_tool_activity_line(*, tool: str, args: str = "") -> str:
    name = tool.strip() or "tool"
    detail = args.strip()
    return f"[tool · {name}] {detail}".rstrip()


def maybe_emit_tool_events(
    emit: EmitFn,
    *,
    agent: str,
    round: int,
    line: str,
) -> None:
    stripped = line.strip()
    if not stripped:
        return

    match = _TOOL_LINE_RE.match(stripped)
    if match:
        tool = match.group("tool").strip() or "tool"
        args = match.group("args").strip()
        payload = {"agent": agent, "round": round, "tool": tool}
        emit("tool_start", {**payload, "args": {"target": args} if args else {}})
        if args:
            emit(
                "tool_output",
                {**payload, "chunk": args},
            )
        emit("tool_done", payload)
        return

    for prefix, tool in _CLI_TOOL_PREFIXES:
        if stripped.startswith(prefix):
            target = stripped[len(prefix) :].strip()
            payload = {"agent": agent, "round": round, "tool": tool}
            emit(
                "tool_start",
                {**payload, "args": {"target": target} if target else {}},
            )
            emit("tool_output", {**payload, "chunk": stripped})
            emit("tool_done", payload)
            return
