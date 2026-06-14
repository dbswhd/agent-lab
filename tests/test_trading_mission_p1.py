"""P1 tests for Trading Mission ingest_bridge."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


from agent_lab.trading_mission.ingest_bridge import (
    apply_critic_cap_to_draft,
    detect_control_plane_db,
    ingest_proposal_batch,
    normalize_proposal_draft,
    use_proposal_critic,
)


def _write_ready_session(
    session: Path,
    *,
    mission_id: str = "2026-06-13-premarket",
    proposals: list[dict] | None = None,
) -> None:
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "market_snapshot.json").write_text(
        json.dumps(
            {
                "trade_allowed": True,
                "eligible_cards": [
                    {
                        "ref": "research/kr/results/overlay/kospi_v1_20260601_full.json",
                        "verdict": "PASS",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (session / "plan.md").write_text(
        "# plan\n\n## 합의\n- ingest_ready: true\n",
        encoding="utf-8",
    )
    (artifacts / "playbook.md").write_text(
        "# 오늘 장중 행동\n\n- approve only\n",
        encoding="utf-8",
    )
    batch = {
        "mission_id": mission_id,
        "session_id": session.name,
        "ingest_ready": True,
        "consensus": {"ingest_ready": True},
        "proposals": proposals
        or [
            {
                "symbol": "069500",
                "market": "kr",
                "side": "buy",
                "quantity": 1,
                "notional": 100000,
                "order_type": "market",
                "thesis": "overlay rebalance into KOSPI ETF",
                "data_sources": ["overlay:kr_kospi_v1"],
                "backtest_ref": "research/kr/results/overlay/kospi_v1_20260601_full.json",
                "confidence": 0.6,
                "expires_at": "2026-06-13T15:20:00+09:00",
            }
        ],
        "generated_at": "2026-06-13T07:30:00+09:00",
    }
    (artifacts / "proposal_batch.json").write_text(
        json.dumps(batch, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_normalize_proposal_draft_ok():
    mapped, err = normalize_proposal_draft(
        {
            "symbol": "069500",
            "market": "kr",
            "side": "buy",
            "quantity": 1,
            "notional": 100000,
            "order_type": "market",
            "thesis": "overlay rebalance into KOSPI ETF",
            "data_sources": ["overlay:kr_kospi_v1"],
            "confidence": 0.6,
            "expires_at": "2026-06-13T15:20:00+09:00",
        },
        mission_id="m1",
        session_id="s1",
    )
    assert err is None
    assert mapped is not None
    assert mapped["proposal"]["symbol"] == "069500"
    assert mapped["proposal"]["approval_status"] == "pending"


def test_normalize_rejects_short_thesis():
    _, err = normalize_proposal_draft(
        {
            "symbol": "069500",
            "side": "buy",
            "quantity": 1,
            "notional": 1,
            "thesis": "short",
            "data_sources": ["x"],
            "confidence": 0.5,
            "expires_at": "2026-06-13T15:20:00+09:00",
        },
        mission_id="m1",
        session_id="s1",
    )
    assert err is not None


def test_ingest_skipped_when_not_ready(tmp_path):
    session = tmp_path / "sess-skip"
    session.mkdir()
    artifacts = session / "artifacts"
    artifacts.mkdir()
    (artifacts / "proposal_batch.json").write_text(
        json.dumps({"mission_id": "m1", "ingest_ready": False, "proposals": []}),
        encoding="utf-8",
    )
    report = ingest_proposal_batch(session, db_path=tmp_path / "cp.sqlite3")
    assert report["ok"] is True
    assert report["skipped"] is True
    assert report["reason"] == "ingest_ready is false"


def test_ingest_writes_sqlite(tmp_path):
    session = tmp_path / "sess-ingest"
    session.mkdir()
    db = tmp_path / "control_plane.sqlite3"
    _write_ready_session(session, mission_id="2026-06-13-test-ingest")

    report = ingest_proposal_batch(session, db_path=db)
    assert report["ok"] is True
    assert report["skipped"] is False
    assert len(report["ingested"]) == 1

    with sqlite3.connect(db) as con:
        row = con.execute("SELECT payload, status FROM trade_proposal").fetchone()
        assert row is not None
        payload = json.loads(row[0])
        assert payload["symbol"] == "069500"
        assert row[1] == "pending"
        evt = con.execute(
            "SELECT event_type FROM audit_event WHERE event_type = ?",
            ("mission_batch_ingested",),
        ).fetchone()
        assert evt is not None


def test_ingest_idempotent_by_mission(tmp_path):
    session = tmp_path / "sess-idem"
    session.mkdir()
    db = tmp_path / "control_plane.sqlite3"
    _write_ready_session(session, mission_id="2026-06-13-idem")

    first = ingest_proposal_batch(session, db_path=db)
    second = ingest_proposal_batch(session, db_path=db)
    assert first["ok"] is True
    assert len(first["ingested"]) == 1
    assert second["skipped"] is True
    assert "already ingested" in second["reason"]

    with sqlite3.connect(db) as con:
        count = con.execute("SELECT COUNT(*) FROM trade_proposal").fetchone()[0]
        assert count == 1


def test_ingest_force_reingest(tmp_path):
    session = tmp_path / "sess-force"
    session.mkdir()
    db = tmp_path / "control_plane.sqlite3"
    _write_ready_session(session, mission_id="2026-06-13-force")

    ingest_proposal_batch(session, db_path=db)
    report = ingest_proposal_batch(session, db_path=db, force=True)
    assert report["ok"] is True
    assert len(report["ingested"]) == 1

    with sqlite3.connect(db) as con:
        count = con.execute("SELECT COUNT(*) FROM trade_proposal").fetchone()[0]
        assert count == 2


def test_ingest_rejects_fail_ref(tmp_path):
    session = tmp_path / "sess-fail"
    session.mkdir()
    db = tmp_path / "control_plane.sqlite3"
    _write_ready_session(
        session,
        mission_id="2026-06-13-fail",
        proposals=[
            {
                "symbol": "069500",
                "market": "kr",
                "side": "buy",
                "quantity": 1,
                "notional": 100000,
                "order_type": "market",
                "thesis": "bad fail ref proposal here",
                "data_sources": ["overlay:kr_kospi_v1"],
                "backtest_ref": "research/kr/results/demo/demo_fail_full.json",
                "confidence": 0.6,
                "expires_at": "2026-06-13T15:20:00+09:00",
            }
        ],
    )
    report = ingest_proposal_batch(session, db_path=db)
    assert report["ok"] is False
    assert report["errors"]


def test_detect_control_plane_db_env(tmp_path, monkeypatch):
    custom = tmp_path / "custom.sqlite3"
    custom.write_text("", encoding="utf-8")
    monkeypatch.setenv("AGENTIC_TRADING_DB", str(custom))
    assert detect_control_plane_db() == custom.resolve()


def test_ingest_applies_critic_cap(tmp_path, monkeypatch):
    pipeline = tmp_path / "pipeline"
    cards = pipeline / "data" / "agentic_trading" / "cards"
    cards.mkdir(parents=True)
    (cards / "kospi_v1.json").write_text(
        json.dumps(
            {
                "ref": "kospi_v1",
                "verdict": "PASS",
                "eligible_for_proposal": True,
                "oos_sharpe": 2.0,
                "fails": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    monkeypatch.setenv("AGENTIC_APPLY_PROPOSAL_CRITIC", "1")
    monkeypatch.delenv("AGENTIC_USE_NATIVE_INGEST", raising=False)

    session = tmp_path / "sess-critic"
    session.mkdir()
    db = tmp_path / "control_plane.sqlite3"
    _write_ready_session(session, mission_id="2026-06-13-critic")

    report = ingest_proposal_batch(session, db_path=db)
    assert report["ok"] is True
    assert report.get("critic_applied") is True
    assert report["critic_reviews"]
    assert report["critic_reviews"][0]["applied_confidence"] <= 0.72

    with sqlite3.connect(db) as con:
        row = con.execute("SELECT payload FROM trade_proposal").fetchone()
        payload = json.loads(row[0])
        assert payload["confidence"] == report["critic_reviews"][0]["applied_confidence"]


def test_normalize_with_critic_enabled(tmp_path, monkeypatch):
    pipeline = tmp_path / "pipeline"
    cards = pipeline / "data" / "agentic_trading" / "cards"
    cards.mkdir(parents=True)
    (cards / "demo_fail.json").write_text(
        json.dumps(
            {
                "ref": "demo_fail",
                "verdict": "FAIL",
                "eligible_for_proposal": False,
                "fails": ["oos"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    monkeypatch.setenv("AGENTIC_APPLY_PROPOSAL_CRITIC", "1")
    assert use_proposal_critic() is True

    draft = {
        "symbol": "069500",
        "market": "kr",
        "side": "buy",
        "quantity": 1,
        "notional": 100000,
        "order_type": "market",
        "thesis": "attempt rebalance with 100k notional",
        "data_sources": ["overlay:kr_kospi_v1"],
        "backtest_ref": "research/kr/results/value_up/demo_fail_full.json",
        "confidence": 0.8,
        "expires_at": "2026-06-13T15:20:00+09:00",
    }
    capped, review = apply_critic_cap_to_draft(draft, {"trade_allowed": True})
    assert review is not None
    assert capped["confidence"] == 0.0

    mapped, err = normalize_proposal_draft(
        draft,
        mission_id="m1",
        session_id="s1",
        snapshot={"trade_allowed": True},
    )
    assert err is None
    assert mapped is not None
    assert mapped["proposal"]["confidence"] == 0.0
    assert mapped["critic_review"]["needs_human"] is True
