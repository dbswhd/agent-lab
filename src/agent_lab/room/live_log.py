"""Append-only live Room SSE log (survives stuck/cancelled turns)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIVE_LOG_NAME = "live.jsonl"

LIVE_EVENT_TYPES = frozenset(
    {
        "agent_start",
        "agent_token",
        "agent_activity",
        "tool_start",
        "tool_output",
        "tool_done",
        "agent_done",
        "agent_error",
        "hook_event",
        "run_cancelled",
        "run_failed",
    }
)


def live_log_path(folder: Path) -> Path:
    return folder / LIVE_LOG_NAME


def clear_live_room_log(folder: Path) -> None:
    live_log_path(folder).unlink(missing_ok=True)


def append_live_room_event(folder: Path, typ: str, payload: dict[str, Any]) -> None:
    if typ not in LIVE_EVENT_TYPES:
        return
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": typ,
        **payload,
    }
    path = live_log_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_live_room_log(folder: Path) -> list[dict[str, Any]]:
    path = live_log_path(folder)
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out
