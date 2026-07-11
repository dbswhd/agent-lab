"""Append-only evidence ledger per session (MB-4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_lab.time_utils import utc_now_iso as _now_iso
from agent_lab.mission.notepad import mission_notepad_dir

DEFAULT_TAIL_LIMIT = 50


def evidence_path(folder: Path) -> Path:
    return mission_notepad_dir(folder) / "evidence.jsonl"


def append_evidence(
    folder: Path,
    event: dict[str, Any],
    *,
    ensure_dir: bool = True,
) -> dict[str, Any]:
    """Append one JSON line to ``.agent-lab/missions/<session_id>/evidence.jsonl``."""
    path = evidence_path(folder)
    if ensure_dir:
        path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(event)
    row.setdefault("at", _now_iso())
    row.setdefault("session_id", folder.name)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    try:
        from agent_lab.run.meta import read_run_meta
        from agent_lab.wisdom.index import build_wisdom_index, wisdom_index_enabled

        if wisdom_index_enabled(read_run_meta(folder)):
            build_wisdom_index(folder, force=True)
    except Exception:
        pass
    return row


def read_evidence_tail(
    folder: Path,
    *,
    limit: int = DEFAULT_TAIL_LIMIT,
) -> list[dict[str, Any]]:
    path = evidence_path(folder)
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, limit) :]:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def public_evidence_payload(folder: Path, *, limit: int = DEFAULT_TAIL_LIMIT) -> dict[str, Any]:
    entries = read_evidence_tail(folder, limit=limit)
    path = evidence_path(folder)
    return {
        "path": str(path),
        "count": len(entries),
        "entries": entries,
    }
