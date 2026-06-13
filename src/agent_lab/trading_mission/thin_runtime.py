"""Thin intraday runtime — playbook/batch/control-plane read only (no Room)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from agent_lab.trading_mission.ingest_bridge import detect_control_plane_db
from agent_lab.research_mcp_read import (
    read_pending_batch_summary,
    read_playbook_summary,
    resolve_session_folder,
)
from agent_lab.session import SESSIONS_DIR


def find_latest_trading_session(*, base: Path | None = None) -> Path | None:
    """Newest session folder with proposal_batch or market_snapshot artifacts."""
    root = base or SESSIONS_DIR
    if not root.is_dir():
        return None

    candidates: list[tuple[float, Path]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        artifacts = child / "artifacts"
        if not artifacts.is_dir():
            continue
        if not (
            (artifacts / "proposal_batch.json").is_file()
            or (artifacts / "market_snapshot.json").is_file()
        ):
            continue
        try:
            mtime = max(
                (artifacts / "proposal_batch.json").stat().st_mtime
                if (artifacts / "proposal_batch.json").is_file()
                else 0,
                (artifacts / "market_snapshot.json").stat().st_mtime
                if (artifacts / "market_snapshot.json").is_file()
                else 0,
                child.stat().st_mtime,
            )
        except OSError:
            mtime = 0.0
        candidates.append((mtime, child))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1].resolve()


def resolve_thin_session_folder() -> Path:
    """AGENT_LAB_SESSION_FOLDER or latest trading mission session."""
    raw = (os.getenv("AGENT_LAB_SESSION_FOLDER") or "").strip()
    if raw:
        folder = Path(raw).expanduser().resolve()
        if folder.is_dir():
            return folder
        raise RuntimeError(f"session folder not found: {folder}")
    latest = find_latest_trading_session()
    if latest is not None:
        return latest
    return resolve_session_folder()


def _pending_from_sqlite(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with sqlite3.connect(db_path) as con:
        try:
            raw = con.execute(
                """
                SELECT p.proposal_id, p.status, p.payload
                FROM trade_proposal p
                WHERE p.status = 'pending'
                ORDER BY p.created_at DESC
                LIMIT 25
                """
            ).fetchall()
        except sqlite3.Error:
            return []
        for proposal_id, status, payload_json in raw:
            symbol = ""
            try:
                payload = json.loads(payload_json)
                symbol = str(payload.get("symbol") or "")
            except json.JSONDecodeError:
                pass
            risk_status = None
            try:
                risk_row = con.execute(
                    """
                    SELECT payload FROM risk_decision
                    WHERE proposal_id = ?
                    ORDER BY checked_at DESC LIMIT 1
                    """,
                    (proposal_id,),
                ).fetchone()
                if risk_row:
                    risk_payload = json.loads(risk_row[0])
                    risk_status = risk_payload.get("status")
            except (json.JSONDecodeError, sqlite3.Error):
                pass
            rows.append(
                {
                    "proposal_id": proposal_id,
                    "symbol": symbol,
                    "status": status,
                    "risk_status": risk_status,
                }
            )
    return rows


def get_intraday_status(
    session_folder: Path | None = None,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Thin runtime status bundle — no Room, no new proposals.
    Uses research MCP read helpers + control plane SQLite.
    """
    folder = session_folder or resolve_thin_session_folder()
    resolved_db = Path(db_path).expanduser().resolve() if db_path else detect_control_plane_db()
    if resolved_db is None:
        resolved_db = Path(os.getenv("AGENTIC_TRADING_DB") or "")

    playbook = read_playbook_summary(folder)
    batch = read_pending_batch_summary(folder)
    pending = _pending_from_sqlite(resolved_db) if resolved_db and resolved_db.is_file() else []

    mission_id = batch.get("mission_id") if batch.get("ok") else None
    return {
        "ok": playbook.get("ok") or batch.get("ok"),
        "session_folder": str(folder),
        "db_path": str(resolved_db) if resolved_db else None,
        "mission_id": mission_id,
        "playbook": {
            "ok": playbook.get("ok"),
            "summary_preview": (playbook.get("summary") or "")[:240],
            "truncated": playbook.get("truncated"),
        },
        "pending_batch": {
            "ok": batch.get("ok"),
            "ingest_ready": batch.get("ingest_ready"),
            "proposal_count": batch.get("proposal_count"),
            "proposals": batch.get("proposals") or [],
        },
        "control_plane_pending": pending,
        "actions_allowed": [
            "read_playbook",
            "read_pending_batch",
            "list_pending_proposals",
            "human_approve_via_console",
        ],
        "actions_forbidden": [
            "full_room_discuss",
            "new_backtest",
            "live_execute",
            "auto_approve",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Thin runtime intraday status (read-only)")
    parser.add_argument("--session", type=Path, default=None, help="Trading mission session folder")
    parser.add_argument("--db", type=Path, default=None, help="Control plane SQLite path")
    args = parser.parse_args(argv)

    if args.session is not None:
        os.environ["AGENT_LAB_SESSION_FOLDER"] = str(args.session.expanduser().resolve())

    payload = get_intraday_status(args.session, db_path=args.db)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
