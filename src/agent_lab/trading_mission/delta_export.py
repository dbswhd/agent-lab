"""Export proposal_delta.json for intraday delta missions (P2)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_lab.trading_mission.export_batch import build_proposal_batch
from agent_lab.trading_mission.topic import mission_id_from_date

_KST = timezone(timedelta(hours=9))


def _default_max_delta_proposals() -> int:
    raw = (os.getenv("AGENT_LAB_TRADING_DELTA_MAX_PROPOSALS") or "3").strip()
    try:
        return max(0, min(int(raw), 10))
    except ValueError:
        return 3


def delta_mission_id(*, suffix: str | None = None) -> str:
    when = datetime.now(_KST)
    base = f"{when.strftime('%Y-%m-%d')}-delta"
    if suffix:
        return f"{base}-{suffix}"
    return f"{base}-{when.strftime('%H%M')}"


def render_delta_topic(*, trigger: str, reason: str = "") -> str:
    when = datetime.now(_KST).strftime("%Y-%m-%d %H:%M KST")
    cap = _default_max_delta_proposals()
    return f"""[Trading Mission — Delta {when}]

## 트리거
- trigger: {trigger}
- reason: {reason or trigger}

## 미션 (짧음 — Room 1라운드만)
1. 최신 snapshot·overlay만 반영해 **TradeProposal 후보** 최대 {cap}건
2. full premarket playbook 대신 **delta patch** + proposal_delta.json
3. backtest execute 금지

## 비목표
- 주문 실행·KIS write
- 2라운드 이상 토론
"""


def build_proposal_delta(
    session_folder: Path,
    *,
    mission_id: str | None = None,
    trigger: str = "manual",
    parent_mission_id: str | None = None,
) -> dict[str, Any]:
    batch = build_proposal_batch(session_folder, mission_id=mission_id or delta_mission_id())
    cap = _default_max_delta_proposals()
    proposals = batch.get("proposals") if isinstance(batch.get("proposals"), list) else []
    trimmed = proposals[:cap]
    mid = mission_id or delta_mission_id()
    parent = parent_mission_id or mission_id_from_date()
    return {
        "mission_id": mid,
        "parent_mission_id": parent,
        "session_id": batch.get("session_id") or session_folder.name,
        "kind": "delta",
        "trigger": trigger,
        "ingest_ready": bool(batch.get("ingest_ready")) and bool(trimmed),
        "consensus": batch.get("consensus") or {},
        "proposals": trimmed,
        "generated_at": datetime.now(_KST).isoformat(),
    }


def write_proposal_delta(session_folder: Path, delta: dict[str, Any]) -> Path:
    artifacts = session_folder / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    out = artifacts / "proposal_delta.json"
    out.write_text(json.dumps(delta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def write_playbook_patch(session_folder: Path, delta: dict[str, Any]) -> Path:
    artifacts = session_folder / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    out = artifacts / "playbook_patch.md"
    trigger = str(delta.get("trigger") or "delta")
    count = len(delta.get("proposals") or [])
    text = f"""# Playbook patch — delta

## 트리거
- {trigger}

## 오늘 장중 행동 (delta)
- pending delta proposals: {count}
- thin agent: 기존 playbook + 이 patch 참고, 신규 full Room 금지
"""
    out.write_text(text, encoding="utf-8")
    return out
