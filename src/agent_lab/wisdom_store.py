"""Cross-session Wisdom Index: persistent JSONL-backed store of agent learnings.

Agents write discoveries once; future sessions recall them via keyword search —
replacing model retraining with an explicit, auditable knowledge base.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class WisdomEntry:
    id: str
    timestamp: str
    content: str
    tags: list[str]
    session_id: str | None = None
    source_ref: str | None = None


def wisdom_index_path() -> Path:
    """Path to the wisdom JSONL file. Override via AGENT_LAB_WISDOM_PATH."""
    override = (os.getenv("AGENT_LAB_WISDOM_PATH") or "").strip()
    if override:
        return Path(override).expanduser()
    from agent_lab.workspace_roots import project_root

    return project_root() / ".agent-lab" / "wisdom.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _entry_id(ts: str, content: str) -> str:
    return "w-" + hashlib.sha1(f"{ts}:{content[:64]}".encode()).hexdigest()[:12]


_store_lock = threading.Lock()


def wisdom_append(
    content: str,
    *,
    tags: list[str] | None = None,
    session_id: str | None = None,
    source_ref: str | None = None,
) -> WisdomEntry:
    """Append a new learning entry. Thread-safe; creates parent dirs if needed."""
    content = content.strip()
    if not content:
        raise ValueError("wisdom content must not be empty")
    ts = _now_iso()
    entry = WisdomEntry(
        id=_entry_id(ts, content),
        timestamp=ts,
        content=content,
        tags=list(tags or []),
        session_id=session_id,
        source_ref=source_ref,
    )
    path = wisdom_index_path()
    with _store_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
    return entry


def wisdom_load(path: Path | None = None) -> list[WisdomEntry]:
    """Load all entries from disk in insertion order."""
    target = path or wisdom_index_path()
    if not target.is_file():
        return []
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return []
    entries: list[WisdomEntry] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        entries.append(
            WisdomEntry(
                id=str(raw.get("id") or ""),
                timestamp=str(raw.get("timestamp") or ""),
                content=str(raw.get("content") or ""),
                tags=list(raw.get("tags") or []),
                session_id=raw.get("session_id"),
                source_ref=raw.get("source_ref"),
            )
        )
    return entries


def _score_entry(entry: WisdomEntry, tokens: list[str]) -> float:
    haystack = f"{entry.content} {' '.join(entry.tags)}".lower()
    score = 0.0
    for token in tokens:
        count = haystack.count(token)
        if count:
            score += count * 10 + 1
    return score


def wisdom_query(query: str, k: int = 5, *, path: Path | None = None) -> list[WisdomEntry]:
    """Keyword search. Returns up to k entries sorted by relevance."""
    entries = wisdom_load(path)
    if not entries or not query.strip():
        return []
    tokens = [t.lower() for t in re.findall(r"[\w가-힣]{2,}", query)]
    if not tokens:
        return []
    scored = [(e, _score_entry(e, tokens)) for e in entries]
    scored = [(e, s) for e, s in scored if s > 0]
    scored.sort(key=lambda x: (-x[1], x[0].timestamp))
    return [e for e, _ in scored[:k]]


def wisdom_list_recent(limit: int = 20, *, path: Path | None = None) -> list[WisdomEntry]:
    """Return the most recent entries, newest first."""
    entries = wisdom_load(path)
    return list(reversed(entries[-limit:])) if entries else []


def wisdom_mcp_enabled() -> bool:
    return os.getenv("AGENT_LAB_WISDOM_MCP", "").strip().lower() in ("1", "true", "yes", "on")


def wisdom_cache_signature() -> tuple[bool]:
    return (wisdom_mcp_enabled(),)


def wisdom_status(path: Path | None = None) -> dict[str, Any]:
    target = path or wisdom_index_path()
    entries = wisdom_load(target)
    return {
        "ok": True,
        "path": str(target),
        "entry_count": len(entries),
        "exists": target.is_file(),
        "newest_at": entries[-1].timestamp if entries else None,
    }
