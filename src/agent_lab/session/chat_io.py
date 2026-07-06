"""Lightweight chat.jsonl loader — no room imports (F12 session↔room cycle break)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_chat_dicts(folder: Path) -> list[dict[str, Any]]:
    """Load chat.jsonl rows as dicts (same tail-lines env as room.session_persist)."""
    chat_path = folder / "chat.jsonl"
    if not chat_path.is_file():
        return []
    raw = os.getenv("AGENT_LAB_CHAT_JSONL_TAIL_LINES")
    tail_lines: int | None = None
    if raw is not None and str(raw).strip():
        try:
            tail_lines = max(0, int(str(raw).strip()))
        except ValueError:
            tail_lines = None
    lines = chat_path.read_text(encoding="utf-8").splitlines()
    if tail_lines is not None and tail_lines > 0 and len(lines) > tail_lines:
        lines = lines[-tail_lines:]
    messages: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            messages.append(data)
    return messages
