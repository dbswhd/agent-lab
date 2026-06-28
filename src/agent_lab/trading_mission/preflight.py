"""Deterministic preflight snapshot for Trading Mission (no LLM)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_lab.pipeline_market_read import (
    read_kill_switch,
    read_overlay_signals,
    read_portfolio_snapshot,
    resolve_freshness_python,
    run_data_freshness,
)
from agent_lab.quant.utility_validation import detect_pipeline_root
from agent_lab.trading_mission.artifact_cards import cards_snapshot_fields, ensure_research_cards

_KST = timezone(timedelta(hours=9))


def _now_kst_iso() -> str:
    return datetime.now(_KST).isoformat()


_resolve_freshness_python = resolve_freshness_python
_run_freshness = run_data_freshness
_overlay_signals = read_overlay_signals
_portfolio_snapshot = read_portfolio_snapshot
_kill_switch = read_kill_switch


def build_market_snapshot(
    pipeline: Path | None = None,
    *,
    as_of: str | None = None,
    sync_cards: bool = True,
) -> dict[str, Any]:
    root = pipeline or detect_pipeline_root()
    if root is None:
        raise FileNotFoundError("pipeline root not found — set QUANT_PIPELINE_ROOT or use ~/Desktop/pipeline")
    root = root.resolve()
    freshness = _run_freshness(root)
    sync_report: dict[str, Any] = {}
    if sync_cards:
        sync_report = ensure_research_cards(root)
    card_fields = cards_snapshot_fields(root, sync_report=sync_report)
    return {
        "as_of": as_of or _now_kst_iso(),
        "pipeline_root": str(root),
        "freshness": freshness,
        "overlay_signals": _overlay_signals(root),
        "portfolio": _portfolio_snapshot(root),
        **card_fields,
        "kill_switch": _kill_switch(root),
        "trade_allowed": not freshness.get("blocking") and not _kill_switch(root),
    }


def write_market_snapshot(session_folder: Path, snapshot: dict[str, Any]) -> Path:
    artifacts = session_folder / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    out = artifacts / "market_snapshot.json"
    out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
