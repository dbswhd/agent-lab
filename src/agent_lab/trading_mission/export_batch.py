"""Build proposal_batch.json from session artifacts + plan.md consensus."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_lab.trading_mission.artifact_cards import proposal_uses_fail_ref
from agent_lab.trading_mission.effective_confidence import (
    batch_context_from_snapshot,
    effective_confidence,
    proposal_needs_human,
)
from agent_lab.trading_mission.topic import mission_id_from_date

_KST = timezone(timedelta(hours=9))
_CONSENSUS_INGEST = re.compile(
    r"ingest_ready\s*:\s*(true|false)",
    re.IGNORECASE,
)
_CONSENSUS_BLOCKING = re.compile(
    r"blocking_reason\s*:\s*(.+)",
    re.IGNORECASE,
)
_CONSENSUS_STRATEGIES = re.compile(
    r"active_strategies\s*:\s*\[([^\]]*)\]",
    re.IGNORECASE,
)


def _parse_consensus(plan_md: str) -> dict[str, Any]:
    text = plan_md or ""
    ingest = False
    m = _CONSENSUS_INGEST.search(text)
    if m:
        ingest = m.group(1).lower() == "true"
    blocking_reason = ""
    m = _CONSENSUS_BLOCKING.search(text)
    if m:
        blocking_reason = m.group(1).strip()
    strategies: list[str] = []
    m = _CONSENSUS_STRATEGIES.search(text)
    if m:
        inner = m.group(1)
        strategies = [s.strip().strip('"').strip("'") for s in inner.split(",") if s.strip()]
    return {
        "ingest_ready": ingest,
        "blocking_reason": blocking_reason,
        "active_strategies": strategies,
    }


def _load_proposals_draft(session_folder: Path) -> list[dict[str, Any]]:
    draft_path = session_folder / "artifacts" / "proposals_draft.json"
    if not draft_path.is_file():
        return []
    try:
        data = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        proposals = data.get("proposals")
        if isinstance(proposals, list):
            return [row for row in proposals if isinstance(row, dict)]
    return []


def _default_expiry() -> str:
    now = datetime.now(_KST)
    close = now.replace(hour=15, minute=20, second=0, microsecond=0)
    if now > close:
        close = close + timedelta(days=1)
    return close.isoformat()


def build_proposal_batch(
    session_folder: Path,
    *,
    mission_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    plan_path = session_folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    consensus = _parse_consensus(plan_md)
    proposals = _load_proposals_draft(session_folder)

    snapshot_path = session_folder / "artifacts" / "market_snapshot.json"
    snap: dict[str, Any] = {}
    trade_allowed = True
    if snapshot_path.is_file():
        try:
            snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
            trade_allowed = bool(snap.get("trade_allowed", True))
        except (OSError, json.JSONDecodeError):
            snap = {}

    pipeline = None
    if snap.get("pipeline_root"):
        pipeline = Path(str(snap["pipeline_root"])).expanduser()

    kept: list[dict[str, Any]] = []
    dropped_fail = 0
    for proposal in proposals:
        if proposal_uses_fail_ref(proposal, snapshot=snap, pipeline=pipeline):
            dropped_fail += 1
            continue
        kept.append(proposal)
    proposals = kept

    ingest_ready = bool(consensus.get("ingest_ready")) and trade_allowed
    if not trade_allowed:
        ingest_ready = False
        if not consensus.get("blocking_reason"):
            consensus["blocking_reason"] = "preflight: trade not allowed"

    for proposal in proposals:
        if "expires_at" not in proposal:
            proposal["expires_at"] = _default_expiry()
        eff = effective_confidence(
            proposal,
            ingest_ready=ingest_ready,
            trade_allowed=trade_allowed,
            snapshot=snap,
            pipeline=pipeline,
        )
        proposal["effective_confidence_preview"] = eff
        proposal["needs_human_preview"] = proposal_needs_human(
            proposal,
            effective=eff,
            snapshot=snap,
            pipeline=pipeline,
            ingest_ready=ingest_ready,
            trade_allowed=trade_allowed,
        )

    mid = mission_id or mission_id_from_date()
    sid = session_id or session_folder.name
    batch: dict[str, Any] = {
        "mission_id": mid,
        "session_id": sid,
        "ingest_ready": ingest_ready,
        "consensus": consensus,
        "proposals": proposals,
        "dropped_fail_refs": dropped_fail,
        "generated_at": datetime.now(_KST).isoformat(),
    }
    if snap:
        batch.update(batch_context_from_snapshot(snap))
    return batch


def write_proposal_batch(session_folder: Path, batch: dict[str, Any]) -> Path:
    artifacts = session_folder / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    out = artifacts / "proposal_batch.json"
    out.write_text(json.dumps(batch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
