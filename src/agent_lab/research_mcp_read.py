"""Read-only helpers for agent-lab research MCP (playbook + pending batch)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from agent_lab.extensions.quant_trading import optional_pipeline_root

_PLAYBOOK_HEADER = re.compile(r"오늘\s*장중\s*행동", re.IGNORECASE)
_THESIS_MAX = 120


def resolve_session_folder() -> Path:
    raw = os.getenv("AGENT_LAB_SESSION_FOLDER", "").strip()
    if not raw:
        raise RuntimeError("AGENT_LAB_SESSION_FOLDER is not set")
    folder = Path(raw).expanduser().resolve()
    if not folder.is_dir():
        raise RuntimeError(f"session folder not found: {folder}")
    return folder


def _playbook_candidates(session_folder: Path | None) -> list[Path]:
    paths: list[Path] = []
    if session_folder is not None:
        paths.append(session_folder / "artifacts" / "playbook.md")
        patch = session_folder / "artifacts" / "playbook_patch.md"
        if patch.is_file():
            paths.append(patch)
    pipeline = optional_pipeline_root()
    if pipeline is not None:
        paths.append(pipeline / "data" / "agentic" / "playbook.md")
    lab_root = (os.getenv("AGENT_LAB_ROOT") or "").strip()
    if lab_root:
        paths.append(Path(lab_root).expanduser() / "data" / "agentic" / "playbook.md")
    return paths


def _extract_intraday_section(text: str) -> str:
    match = _PLAYBOOK_HEADER.search(text)
    if match is None:
        return text.strip()
    return text[match.start() :].strip()


def read_playbook_summary(
    session_folder: Path | None = None,
    *,
    max_chars: int = 4000,
) -> dict[str, Any]:
    """Return compact playbook text for thin runtime agent (token-safe)."""
    folder = session_folder
    if folder is None:
        try:
            folder = resolve_session_folder()
        except RuntimeError:
            folder = None

    for path in _playbook_candidates(folder):
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        section = _extract_intraday_section(raw)
        truncated = len(section) > max_chars
        summary = section[:max_chars] if truncated else section
        return {
            "ok": True,
            "path": str(path),
            "summary": summary,
            "truncated": truncated,
            "char_count": len(section),
        }

    return {
        "ok": False,
        "reason": "playbook not found",
        "checked": [str(p) for p in _playbook_candidates(folder)],
    }


def _compact_proposal(row: dict[str, Any]) -> dict[str, Any]:
    thesis = str(row.get("thesis") or "").strip()
    if len(thesis) > _THESIS_MAX:
        thesis = thesis[: _THESIS_MAX - 1] + "…"
    return {
        "symbol": str(row.get("symbol") or "").strip().upper(),
        "market": str(row.get("market") or "kr").strip().lower(),
        "side": str(row.get("side") or "").strip().lower(),
        "notional": float(row.get("notional") or 0),
        "backtest_ref": row.get("backtest_ref"),
        "confidence": row.get("confidence"),
        "thesis_preview": thesis or None,
    }


def read_pending_batch_summary(session_folder: Path | None = None) -> dict[str, Any]:
    """Return proposal_batch.json / proposal_delta.json summary (no full Room context)."""
    folder = session_folder or resolve_session_folder()
    artifacts = folder / "artifacts"
    source_name: str | None = None
    batch: dict[str, Any] | None = None
    for name in ("proposal_delta.json", "proposal_batch.json"):
        path = artifacts / name
        if not path.is_file():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(loaded, dict):
            batch = loaded
            source_name = name
            break

    if batch is None:
        return {
            "ok": False,
            "reason": "proposal batch missing",
            "session_folder": str(folder),
            "checked": [
                str(artifacts / "proposal_batch.json"),
                str(artifacts / "proposal_delta.json"),
            ],
        }

    proposals_raw = batch.get("proposals") if isinstance(batch.get("proposals"), list) else []
    compact = [
        _compact_proposal(row)
        for row in proposals_raw
        if isinstance(row, dict)
    ]

    return {
        "ok": True,
        "source": source_name or "proposal_batch.json",
        "session_folder": str(folder),
        "mission_id": str(batch.get("mission_id") or ""),
        "session_id": str(batch.get("session_id") or folder.name),
        "ingest_ready": bool(batch.get("ingest_ready")),
        "generated_at": batch.get("generated_at"),
        "proposal_count": len(compact),
        "proposals": compact,
    }
