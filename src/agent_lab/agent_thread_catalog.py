from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.app_config import resolve_sessions_dir

AGENT_IDS = ("cursor", "codex", "claude")


def _sessions_dir() -> Path:
    return Path(os.getenv("AGENT_LAB_SESSIONS_DIR", str(resolve_sessions_dir())))


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def relative_last_label(when: datetime | None) -> str:
    if when is None:
        return "—"
    now = datetime.now(timezone.utc)
    delta = max(0, int((now - when.astimezone(timezone.utc)).total_seconds()))
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86_400:
        return f"{delta // 3600}h"
    return f"{delta // 86_400}d"


def _read_meta(folder: Path) -> dict[str, Any]:
    meta_path = folder / "meta.json"
    if not meta_path.is_file():
        return {}
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _session_topic(folder: Path, meta: dict[str, Any]) -> str:
    topic_path = folder / "topic.txt"
    if topic_path.is_file():
        topic = topic_path.read_text(encoding="utf-8").strip()
        if topic:
            return topic
    return str(meta.get("topic") or folder.name)


def _agent_stats(folder: Path) -> tuple[dict[str, int], datetime | None]:
    counts: dict[str, int] = {a: 0 for a in AGENT_IDS}
    latest: datetime | None = None
    chat_path = folder / "chat.jsonl"
    if not chat_path.is_file():
        return counts, latest
    for line in chat_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        agent = str(row.get("agent") or "").strip().lower()
        if agent not in counts:
            continue
        counts[agent] += 1
        ts = _parse_ts(str(row.get("ts") or ""))
        if ts and (latest is None or ts > latest):
            latest = ts
    return counts, latest


def list_agent_threads(
    *,
    limit_per_agent: int = 8,
    sessions_root: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Recent Agent Lab sessions where each agent participated (resume picker)."""
    root = sessions_root or _sessions_dir()
    buckets: dict[str, list[dict[str, Any]]] = {a: [] for a in AGENT_IDS}
    if not root.is_dir():
        return buckets

    candidates: list[tuple[datetime, Path, dict[str, Any]]] = []
    for path in root.iterdir():
        if not path.is_dir() or path.name.startswith("."):
            continue
        meta = _read_meta(path)
        if meta.get("archived"):
            continue
        created = _parse_ts(str(meta.get("created_at") or ""))
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        sort_ts = created or mtime
        candidates.append((sort_ts, path, meta))

    candidates.sort(key=lambda row: row[0], reverse=True)

    for _sort_ts, folder, meta in candidates:
        counts, chat_latest = _agent_stats(folder)
        topic = _session_topic(folder, meta)
        created = _parse_ts(str(meta.get("created_at") or ""))
        last_dt = chat_latest or created or _sort_ts
        last_label = relative_last_label(last_dt)
        session_id = folder.name
        for agent in AGENT_IDS:
            msgs = counts.get(agent, 0)
            if msgs <= 0:
                continue
            if len(buckets[agent]) >= limit_per_agent:
                continue
            label = topic if len(topic) <= 56 else f"{topic[:53]}…"
            buckets[agent].append(
                {
                    "id": session_id,
                    "label": label,
                    "msgs": msgs,
                    "last": last_label,
                }
            )
    return buckets


def normalize_agent_thread_bindings(raw: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(raw, dict):
        return out
    for agent in AGENT_IDS:
        val = raw.get(agent)
        if val is None:
            continue
        text = str(val).strip().lower()
        if not text or text == "new":
            out[agent] = "new"
            continue
        folder = _sessions_dir() / text
        if folder.is_dir():
            out[agent] = text
    return out
