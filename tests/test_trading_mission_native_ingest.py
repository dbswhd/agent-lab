"""Tests for native ingest delegate (AGENTIC_USE_NATIVE_INGEST)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agent_lab.trading_mission.ingest_bridge import ingest_proposal_batch
from agent_lab.trading_mission.native_ingest import (
    native_ingest_session_folder,
    resolve_quant_pipeline_src,
    use_native_ingest,
)
from agent_lab.trading_mission.native_ingest import _normalize_native_report

pytestmark = [pytest.mark.integration, pytest.mark.quant]


def _write_ready_session(session: Path, *, mission_id: str = "2026-06-13-native") -> None:
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "market_snapshot.json").write_text(
        json.dumps({"trade_allowed": True, "eligible_cards": []}),
        encoding="utf-8",
    )
    (session / "plan.md").write_text("# plan\n\n## 합의\n- ingest_ready: true\n", encoding="utf-8")
    (artifacts / "playbook.md").write_text("# 오늘 장중 행동\n\n- approve\n", encoding="utf-8")
    batch = {
        "mission_id": mission_id,
        "session_id": session.name,
        "ingest_ready": True,
        "proposals": [
            {
                "symbol": "069500",
                "market": "kr",
                "side": "buy",
                "quantity": 1,
                "notional": 100_000,
                "order_type": "market",
                "thesis": "overlay rebalance into KOSPI ETF position",
                "data_sources": ["overlay:kr_kospi_v1"],
                "backtest_ref": "research/kr/results/overlay/kospi_v1_pass_full.json",
                "confidence": 0.6,
                "expires_at": "2026-06-13T15:20:00+09:00",
            }
        ],
    }
    (artifacts / "proposal_batch.json").write_text(
        json.dumps(batch, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_use_native_ingest_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGENTIC_USE_NATIVE_INGEST", raising=False)
    assert use_native_ingest() is False
    monkeypatch.setenv("AGENTIC_USE_NATIVE_INGEST", "1")
    assert use_native_ingest() is True


def test_normalize_native_report_maps_ids():
    report = _normalize_native_report(
        {
            "ok": True,
            "ingested": [
                {
                    "proposal_id": "tp_abc",
                    "symbol": "069500",
                    "risk_status": "needs_human",
                }
            ],
        }
    )
    assert report["ingested"] == ["tp_abc"]
    assert report["ingested_details"][0]["risk_status"] == "needs_human"


def test_native_ingest_writes_risk_decision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = resolve_quant_pipeline_src()
    if src is None:
        pytest.skip("quant_pipeline src not found")

    monkeypatch.setenv("AGENTIC_USE_NATIVE_INGEST", "1")
    monkeypatch.setenv("AGENTIC_QUANT_PIPELINE_SRC", str(src))

    session = tmp_path / "sess-native"
    session.mkdir()
    db = tmp_path / "native_cp.sqlite3"
    mission_id = "2026-06-13-native-risk"
    _write_ready_session(session, mission_id=mission_id)

    report = ingest_proposal_batch(session, db_path=db)
    assert report["ok"] is True
    assert report.get("ingest_backend") == "native"
    assert len(report["ingested"]) == 1
    assert report.get("ingested_details")
    assert report["ingested_details"][0].get("risk_status")

    with sqlite3.connect(db) as con:
        proposals = con.execute("SELECT COUNT(*) FROM trade_proposal").fetchone()[0]
        risks = con.execute("SELECT COUNT(*) FROM risk_decision").fetchone()[0]
        assert proposals == 1
        assert risks == 1


def test_native_ingest_direct_call_dry_run(tmp_path: Path):
    src = resolve_quant_pipeline_src()
    if src is None:
        pytest.skip("quant_pipeline src not found")

    session = tmp_path / "sess-dry"
    session.mkdir()
    db = tmp_path / "dry.sqlite3"
    _write_ready_session(session, mission_id="2026-06-13-native-dry")

    report = native_ingest_session_folder(session, db_path=db, dry_run=True)
    assert report["ok"] is True
    assert report["ingested_details"][0]["dry_run"] is True
    assert con_rows(db) == 0


def con_rows(db: Path) -> int:
    if not db.is_file():
        return 0
    with sqlite3.connect(db) as con:
        try:
            return int(con.execute("SELECT COUNT(*) FROM trade_proposal").fetchone()[0])
        except sqlite3.OperationalError:
            return 0
