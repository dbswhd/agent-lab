"""Append-only live Room SSE log (survives stuck/cancelled turns)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIVE_LOG_NAME = "live.jsonl"
LIVE_ARCHIVE_DIR = "live_archives"

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
        "inbox_pending",
    }
)


def live_log_path(folder: Path) -> Path:
    return folder / LIVE_LOG_NAME


def live_archive_dir(folder: Path) -> Path:
    return folder / LIVE_ARCHIVE_DIR


def clear_live_room_log(folder: Path) -> None:
    live_log_path(folder).unlink(missing_ok=True)


def archive_live_room_log(folder: Path, turn_index: int) -> None:
    """Move the in-flight log into ``live_archives/`` before the next turn."""
    src = live_log_path(folder)
    if not src.is_file():
        return
    dest_dir = live_archive_dir(folder)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"turn-{max(1, turn_index):04d}.jsonl"
    if dest.exists():
        dest.unlink()
    src.replace(dest)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def read_archived_live_room_logs(folder: Path) -> list[dict[str, Any]]:
    dest_dir = live_archive_dir(folder)
    if not dest_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(dest_dir.glob("turn-*.jsonl")):
        out.extend(_read_jsonl(path))
    return out


def read_session_live_log(folder: Path) -> list[dict[str, Any]]:
    """Archived turn logs plus the current in-flight log (chronological)."""
    return read_archived_live_room_logs(folder) + read_live_room_log(folder)


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
    return _read_jsonl(live_log_path(folder))
