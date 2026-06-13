"""Ingest proposal_batch.json into Agentic Trading control plane SQLite (P1)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_lab.trading_mission.verify import _proposal_has_fail_ref

from agent_lab.trading_mission.effective_confidence import effective_confidence

_BLOCKED_THESIS = (
    "ignore previous",
    "bypass risk",
    "override risk",
    "disable guard",
    "place this live order",
)
_MARKET = frozenset({"kr", "us"})
_SIDE = frozenset({"buy", "sell"})
_ORDER_TYPE = frozenset({"market", "limit"})
_CRITIC_ENV = "AGENTIC_APPLY_PROPOSAL_CRITIC"


def use_proposal_critic() -> bool:
    raw = (os.getenv(_CRITIC_ENV) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _critic_ref_from_draft(draft: dict[str, Any]) -> str:
    backtest_ref = str(draft.get("backtest_ref") or "").strip()
    if backtest_ref:
        return backtest_ref
    for source in draft.get("data_sources") or []:
        text = str(source).strip()
        if text.startswith("card:"):
            return text.split(":", 1)[-1]
    return ""


def _quote_context_from_snapshot(snapshot: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    quote: dict[str, Any] = {}
    freshness = snapshot.get("freshness")
    if isinstance(freshness, dict):
        quote["freshness"] = freshness
    symbol = str(draft.get("symbol") or "").strip().upper()
    if symbol:
        quote["symbol"] = symbol
    return quote


def apply_critic_cap_to_draft(
    draft: dict[str, Any],
    snapshot: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return draft with capped confidence and compact critic review."""
    from agent_lab.proposal_critic import apply_confidence_cap, review_proposal_thesis

    ref = _critic_ref_from_draft(draft)
    try:
        agent_confidence = float(draft.get("confidence", 0))
    except (TypeError, ValueError):
        agent_confidence = 0.0

    review = review_proposal_thesis(
        str(draft.get("thesis") or ""),
        ref,
        _quote_context_from_snapshot(snapshot, draft),
        symbol=str(draft.get("symbol") or "") or None,
        agent_confidence=agent_confidence,
    )
    capped = apply_confidence_cap(agent_confidence, review)
    updated = dict(draft)
    updated["confidence"] = capped
    compact_review = {
        "ref": review.get("ref"),
        "objections": review.get("objections") or [],
        "missing_evidence": review.get("missing_evidence") or [],
        "confidence_cap": review.get("confidence_cap"),
        "needs_human": review.get("needs_human"),
        "applied_confidence": capped,
        "source": review.get("source"),
    }
    updated["critic_review"] = {
        "objections": compact_review["objections"],
        "missing_evidence": compact_review["missing_evidence"],
        "confidence_cap": compact_review["confidence_cap"],
        "needs_human": compact_review["needs_human"],
        "ref": compact_review["ref"],
    }
    return updated, compact_review


def apply_critic_caps_to_proposals(
    proposals: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply critic cap to each proposal when AGENTIC_APPLY_PROPOSAL_CRITIC=1."""
    if not use_proposal_critic():
        return proposals, []

    updated: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    for idx, row in enumerate(proposals):
        if not isinstance(row, dict):
            updated.append(row)
            continue
        capped_row, review = apply_critic_cap_to_draft(row, snapshot)
        updated.append(capped_row)
        if review is not None:
            reviews.append({"index": idx, **review})
    return updated, reviews


def detect_control_plane_db() -> Path | None:
    """Resolve control plane SQLite path from env or agentic-trading extension locations."""
    from agent_lab.extensions.quant_trading import optional_agentic_db

    resolved = optional_agentic_db()
    if resolved is not None:
        return resolved

    default = Path.home() / ".agent-lab" / "control_plane.sqlite3"
    default.parent.mkdir(parents=True, exist_ok=True)
    return default.resolve()


def _parse_expires_at(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    text = str(raw).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _normalize_data_sources(raw: Any) -> list[str]:
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return parts
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def normalize_proposal_draft(
    draft: dict[str, Any],
    *,
    mission_id: str,
    session_id: str,
    snapshot: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Map Lab draft row to control-plane TradeProposal JSON payload."""
    working = draft
    critic_review: dict[str, Any] | None = None
    if use_proposal_critic() and snapshot is not None:
        working, critic_review = apply_critic_cap_to_draft(draft, snapshot)

    symbol = str(working.get("symbol") or "").strip().upper()
    if not symbol:
        return None, "symbol is required"

    market = str(working.get("market") or "kr").strip().lower()
    if market not in _MARKET:
        return None, f"invalid market: {market}"

    side = str(working.get("side") or "").strip().lower()
    if side not in _SIDE:
        return None, f"invalid side: {side}"

    order_type = str(working.get("order_type") or "market").strip().lower()
    if order_type not in _ORDER_TYPE:
        return None, f"invalid order_type: {order_type}"

    try:
        quantity = int(working.get("quantity") or 0)
    except (TypeError, ValueError):
        return None, "quantity must be int"
    if quantity <= 0:
        return None, "quantity must be > 0"

    try:
        notional = float(working.get("notional") or 0)
    except (TypeError, ValueError):
        return None, "notional must be number"
    if notional <= 0:
        return None, "notional must be > 0"

    thesis = str(working.get("thesis") or "").strip()
    if len(thesis) < 12:
        return None, "thesis must be at least 12 characters"
    lowered = thesis.lower()
    if any(token in lowered for token in _BLOCKED_THESIS):
        return None, "thesis contains unsafe instruction text"

    data_sources = _normalize_data_sources(working.get("data_sources"))
    if not data_sources:
        return None, "data_sources is required"

    try:
        agent_confidence = float(working.get("confidence", 0))
    except (TypeError, ValueError):
        return None, "confidence must be number"
    if agent_confidence < 0 or agent_confidence > 1:
        return None, "confidence must be between 0 and 1"

    trade_allowed = None
    if snapshot is not None and "trade_allowed" in snapshot:
        trade_allowed = bool(snapshot.get("trade_allowed"))
    confidence = effective_confidence(
        working,
        ingest_ready=True,
        trade_allowed=trade_allowed,
        snapshot=snapshot,
    )

    expires_at = _parse_expires_at(working.get("expires_at"))
    if expires_at is None:
        return None, "expires_at is required"

    limit_price: float | None = None
    if working.get("limit_price") is not None:
        try:
            limit_price = float(working["limit_price"])
        except (TypeError, ValueError):
            return None, "limit_price must be number"
        if limit_price <= 0:
            return None, "limit_price must be > 0"

    backtest_ref = working.get("backtest_ref")
    if backtest_ref is not None:
        backtest_ref = str(backtest_ref).strip() or None

    proposal_id = str(working.get("proposal_id") or f"tp_{uuid4().hex}")
    created_at = datetime.now(UTC)

    payload: dict[str, Any] = {
        "proposal_id": proposal_id,
        "symbol": symbol,
        "market": market,
        "side": side,
        "quantity": quantity,
        "notional": notional,
        "order_type": order_type,
        "limit_price": limit_price,
        "thesis": thesis,
        "data_sources": data_sources,
        "backtest_ref": backtest_ref,
        "confidence": confidence,
        "expires_at": expires_at.isoformat(),
        "created_at": created_at.isoformat(),
        "approval_status": "pending",
    }
    agent_prompt = (
        f"trading_mission:{mission_id} session:{session_id} "
        f"source:agent-lab/trading_mission/ingest_bridge"
    )
    result: dict[str, Any] = {"proposal": payload, "agent_prompt": agent_prompt}
    if critic_review is not None:
        result["critic_review"] = critic_review
    return result, None


def _ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS trade_proposal (
            proposal_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS risk_decision (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            checked_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approval (
            approval_id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            approved_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS execution (
            execution_id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            submitted_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _mission_already_ingested(con: sqlite3.Connection, mission_id: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM audit_event WHERE event_type = ? AND entity_id = ? LIMIT 1",
        ("mission_batch_ingested", mission_id),
    ).fetchone()
    return row is not None


def _insert_proposal(
    con: sqlite3.Connection,
    payload: dict[str, Any],
    agent_prompt: str,
) -> str:
    proposal_id = str(payload["proposal_id"])
    con.execute(
        "INSERT INTO trade_proposal(proposal_id, payload, status, created_at) VALUES (?, ?, ?, ?)",
        (
            proposal_id,
            json.dumps(payload, ensure_ascii=False),
            payload["approval_status"],
            payload["created_at"],
        ),
    )
    event_payload = json.dumps(
        {"proposal": payload, "agent_prompt": agent_prompt},
        ensure_ascii=False,
    )
    con.execute(
        "INSERT INTO audit_event(event_id, event_type, entity_id, payload) VALUES (?, ?, ?, ?)",
        (
            f"evt_{uuid4().hex}",
            "proposal_created",
            proposal_id,
            event_payload,
        ),
    )
    return proposal_id


def _record_mission_ingest(
    con: sqlite3.Connection,
    *,
    mission_id: str,
    session_id: str,
    proposal_ids: list[str],
    ingest_ready: bool,
) -> None:
    payload = json.dumps(
        {
            "mission_id": mission_id,
            "session_id": session_id,
            "ingest_ready": ingest_ready,
            "proposal_ids": proposal_ids,
            "ingested_at": datetime.now(UTC).isoformat(),
        },
        ensure_ascii=False,
    )
    con.execute(
        "INSERT INTO audit_event(event_id, event_type, entity_id, payload) VALUES (?, ?, ?, ?)",
        (
            f"evt_{uuid4().hex}",
            "mission_batch_ingested",
            mission_id,
            payload,
        ),
    )


def load_proposal_batch(session_folder: Path) -> dict[str, Any] | None:
    artifacts = session_folder / "artifacts"
    for name in ("proposal_batch.json", "proposal_delta.json"):
        path = artifacts / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _batch_file_path(session_folder: Path) -> Path | None:
    artifacts = session_folder / "artifacts"
    for name in ("proposal_batch.json", "proposal_delta.json"):
        path = artifacts / name
        if path.is_file():
            return path
    return None


def _persist_capped_batch(
    session_folder: Path,
    batch: dict[str, Any],
    proposals: list[dict[str, Any]],
) -> tuple[Path | None, str | None]:
    """Write critic-capped proposals back to batch file; return path + backup text."""
    path = _batch_file_path(session_folder)
    if path is None:
        return None, None
    backup = path.read_text(encoding="utf-8")
    updated = dict(batch)
    updated["proposals"] = proposals
    path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, backup


def ingest_proposal_batch(
    session_folder: Path,
    *,
    db_path: Path | str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Ingest session proposal_batch.json into control plane SQLite."""
    folder = session_folder.expanduser().resolve()
    batch = load_proposal_batch(folder)
    if batch is None:
        return {
            "ok": False,
            "skipped": True,
            "reason": "proposal_batch.json missing",
            "ingested": [],
            "errors": [],
        }

    mission_id = str(batch.get("mission_id") or "")
    session_id = str(batch.get("session_id") or folder.name)
    ingest_ready = bool(batch.get("ingest_ready"))
    proposals = batch.get("proposals") if isinstance(batch.get("proposals"), list) else []

    snapshot_path = folder / "artifacts" / "market_snapshot.json"
    snapshot: dict[str, Any] = {}
    if snapshot_path.is_file():
        try:
            loaded = json.loads(snapshot_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                snapshot = loaded
        except (OSError, json.JSONDecodeError):
            pass

    if not ingest_ready:
        return {
            "ok": True,
            "skipped": True,
            "reason": "ingest_ready is false",
            "mission_id": mission_id,
            "session_id": session_id,
            "ingested": [],
            "errors": [],
        }

    if not proposals:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no proposals in batch",
            "mission_id": mission_id,
            "session_id": session_id,
            "ingested": [],
            "errors": [],
        }

    resolved_db = Path(db_path).expanduser().resolve() if db_path else detect_control_plane_db()
    if resolved_db is None:
        return {
            "ok": False,
            "skipped": True,
            "reason": "control plane db path not found",
            "mission_id": mission_id,
            "session_id": session_id,
            "ingested": [],
            "errors": [],
        }

    from agent_lab.trading_mission.native_ingest import native_ingest_session_folder, use_native_ingest

    critic_reviews: list[dict[str, Any]] = []
    batch_path: Path | None = None
    batch_backup: str | None = None
    if use_proposal_critic() and use_native_ingest():
        proposals, critic_reviews = apply_critic_caps_to_proposals(proposals, snapshot)
        batch_path, batch_backup = _persist_capped_batch(folder, batch, proposals)

    if use_native_ingest():
        try:
            native_report = native_ingest_session_folder(
                folder,
                db_path=resolved_db,
                force=force,
                dry_run=dry_run,
            )
            native_report.setdefault("mission_id", mission_id)
            native_report.setdefault("session_id", session_id)
            if critic_reviews:
                native_report["critic_reviews"] = critic_reviews
                native_report["critic_applied"] = True
            return native_report
        finally:
            if batch_backup is not None and batch_path is not None:
                batch_path.write_text(batch_backup, encoding="utf-8")

    normalized: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    critic_reviews_from_normalize: list[dict[str, Any]] = []
    for idx, row in enumerate(proposals):
        if not isinstance(row, dict):
            errors.append({"index": str(idx), "error": "proposal must be object"})
            continue
        if _proposal_has_fail_ref(row, snapshot):
            errors.append({"index": str(idx), "error": "FAIL backtest_ref"})
            continue
        mapped, err = normalize_proposal_draft(
            row,
            mission_id=mission_id,
            session_id=session_id,
            snapshot=snapshot,
        )
        if err or mapped is None:
            errors.append({"index": str(idx), "error": err or "normalize failed"})
            continue
        review = mapped.get("critic_review")
        if isinstance(review, dict):
            critic_reviews_from_normalize.append(
                {"index": idx, "proposal_id": mapped["proposal"]["proposal_id"], **review}
            )
        normalized.append(mapped)

    if errors:
        return {
            "ok": False,
            "skipped": False,
            "reason": "proposal validation failed",
            "mission_id": mission_id,
            "session_id": session_id,
            "db_path": str(resolved_db),
            "ingested": [],
            "errors": errors,
        }

    if dry_run:
        report = {
            "ok": True,
            "skipped": False,
            "dry_run": True,
            "mission_id": mission_id,
            "session_id": session_id,
            "db_path": str(resolved_db),
            "ingested": [m["proposal"]["proposal_id"] for m in normalized],
            "errors": [],
        }
        if critic_reviews_from_normalize:
            report["critic_reviews"] = critic_reviews_from_normalize
            report["critic_applied"] = True
        return report

    resolved_db.parent.mkdir(parents=True, exist_ok=True)
    ingested_ids: list[str] = []
    with sqlite3.connect(resolved_db) as con:
        _ensure_schema(con)
        if mission_id and _mission_already_ingested(con, mission_id) and not force:
            return {
                "ok": True,
                "skipped": True,
                "reason": f"mission already ingested: {mission_id}",
                "mission_id": mission_id,
                "session_id": session_id,
                "db_path": str(resolved_db),
                "ingested": [],
                "errors": [],
            }

        try:
            for item in normalized:
                pid = _insert_proposal(con, item["proposal"], item["agent_prompt"])
                ingested_ids.append(pid)
            if mission_id:
                _record_mission_ingest(
                    con,
                    mission_id=mission_id,
                    session_id=session_id,
                    proposal_ids=ingested_ids,
                    ingest_ready=True,
                )
            con.commit()
        except sqlite3.Error as exc:
            con.rollback()
            return {
                "ok": False,
                "skipped": False,
                "reason": f"sqlite error: {exc}",
                "mission_id": mission_id,
                "session_id": session_id,
                "db_path": str(resolved_db),
                "ingested": [],
                "errors": [{"index": "*", "error": str(exc)}],
            }

    report = {
        "ok": True,
        "skipped": False,
        "mission_id": mission_id,
        "session_id": session_id,
        "db_path": str(resolved_db),
        "ingested": ingested_ids,
        "errors": [],
    }
    if critic_reviews_from_normalize:
        report["critic_reviews"] = critic_reviews_from_normalize
        report["critic_applied"] = True
    return report
