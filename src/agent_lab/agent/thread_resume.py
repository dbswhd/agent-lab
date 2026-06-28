from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_lab.agent.thread_catalog import AGENT_IDS, normalize_agent_thread_bindings
from agent_lab.app_config import resolve_sessions_dir


def _sessions_root() -> Path:
    return Path(os.getenv("AGENT_LAB_SESSIONS_DIR", str(resolve_sessions_dir())))


def _session_topic(folder: Path) -> str:
    topic_path = folder / "topic.txt"
    if topic_path.is_file():
        topic = topic_path.read_text(encoding="utf-8").strip()
        if topic:
            return topic
    meta_path = folder / "meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            topic = str(meta.get("topic") or "").strip()
            if topic:
                return topic
        except json.JSONDecodeError:
            pass
    return folder.name


def _agent_excerpt(folder: Path, agent: str, *, max_lines: int = 4) -> list[str]:
    chat_path = folder / "chat.jsonl"
    if not chat_path.is_file():
        return []
    rows: list[str] = []
    for line in chat_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("agent") or "").strip().lower() != agent:
            continue
        body = str(row.get("content") or "").strip()
        if body:
            rows.append(body)
    if not rows:
        return []
    tail = rows[-max_lines:]
    clipped: list[str] = []
    for text in tail:
        clipped.append(text if len(text) <= 320 else f"{text[:317]}…")
    return clipped


def build_agent_thread_resume_block(agent: str, run_meta: dict[str, Any] | None) -> str:
    aid = agent.strip().lower()
    if aid not in AGENT_IDS:
        return ""
    bindings = normalize_agent_thread_bindings((run_meta or {}).get("agent_thread_bindings"))
    src_id = bindings.get(aid, "new")
    if not src_id or src_id == "new":
        return ""
    folder = _sessions_root() / src_id
    if not folder.is_dir():
        return ""
    topic = _session_topic(folder)
    excerpts = _agent_excerpt(folder, aid)
    lines = [
        f"[Agent thread resume — {aid}]",
        f"Continuing from Agent Lab session `{src_id}` ({topic}).",
        "Treat prior work as context; do not assume the human sees that session unless referenced.",
    ]
    if excerpts:
        lines.append("Recent replies from that session:")
        for i, text in enumerate(excerpts, start=1):
            lines.append(f"{i}. {text}")
    return "\n".join(lines)
