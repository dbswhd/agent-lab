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
