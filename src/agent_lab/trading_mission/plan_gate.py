"""Trading Mission Momus-lite plan gate extensions (P1)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_lab.trading_mission.export_batch import _parse_consensus
from agent_lab.trading_mission.verify import _proposal_has_fail_ref

_PLAYBOOK_HEADER = re.compile(r"오늘\s*장중\s*행동", re.IGNORECASE)
_INGEST_READY = re.compile(r"ingest_ready\s*:\s*(true|false)", re.IGNORECASE)


def trading_plan_gate_issues(
    plan_md: str,
    session_folder: Path,
) -> list[str]:
    """Return mechanical checklist failures for trading-mission plan.md."""
    issues: list[str] = []
    text = plan_md or ""
    if "## 합의" not in text:
        issues.append("missing_consensus_section")
        return issues

    if not _INGEST_READY.search(text):
        issues.append("missing_ingest_ready")
        return issues

    consensus = _parse_consensus(text)
    ingest_ready = bool(consensus.get("ingest_ready"))
    artifacts = session_folder / "artifacts"

    snap_path = artifacts / "market_snapshot.json"
    if not snap_path.is_file():
        issues.append("missing_market_snapshot")

    batch_path = artifacts / "proposal_batch.json"
    if not batch_path.is_file():
        issues.append("missing_proposal_batch")

    playbook_path = artifacts / "playbook.md"
    if not playbook_path.is_file():
        issues.append("missing_playbook")
    elif playbook_path.is_file():
        pb_text = playbook_path.read_text(encoding="utf-8", errors="replace")
        if not _PLAYBOOK_HEADER.search(pb_text):
            issues.append("playbook_missing_intraday_section")

    snapshot: dict[str, Any] = {}
    if snap_path.is_file():
        try:
            loaded = json.loads(snap_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                snapshot = loaded
        except (OSError, json.JSONDecodeError):
            issues.append("invalid_market_snapshot")

    if ingest_ready and not snapshot.get("trade_allowed", True):
        issues.append("ingest_ready_true_but_trade_not_allowed")

    proposals: list[dict[str, Any]] = []
    if batch_path.is_file():
        try:
            batch = json.loads(batch_path.read_text(encoding="utf-8"))
            if isinstance(batch, dict):
                raw = batch.get("proposals")
                if isinstance(raw, list):
                    proposals = [p for p in raw if isinstance(p, dict)]
                if ingest_ready and not bool(batch.get("ingest_ready")):
                    issues.append("batch_ingest_ready_false")
        except (OSError, json.JSONDecodeError):
            issues.append("invalid_proposal_batch")

    if ingest_ready and not proposals:
        issues.append("ingest_ready_true_but_no_proposals")

    for proposal in proposals:
        if _proposal_has_fail_ref(proposal, snapshot):
            issues.append("fail_backtest_ref_in_proposals")
            break
        ref = str(proposal.get("backtest_ref") or "").strip()
        sources = proposal.get("data_sources")
        has_overlay = isinstance(sources, list) and any("overlay" in str(s).lower() for s in sources)
        if not ref and not has_overlay:
            issues.append("proposal_missing_ref")
            break

    return issues
