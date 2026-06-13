"""Tests for research MCP light (get_playbook, get_pending_batch)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.research_mcp_read import read_pending_batch_summary, read_playbook_summary


def _write_trading_session(session: Path) -> None:
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "playbook.md").write_text(
        "# Trading Mission\n\n"
        "## 오늘 장중 행동\n\n"
        "- Approve only PASS ref proposals\n"
        "- No new backtest during market hours\n",
        encoding="utf-8",
    )
    batch = {
        "mission_id": "2026-06-13-premarket",
        "session_id": session.name,
        "ingest_ready": True,
        "generated_at": "2026-06-13T07:30:00+09:00",
        "proposals": [
            {
                "symbol": "069500",
                "market": "kr",
                "side": "buy",
                "quantity": 1,
                "notional": 100_000,
                "order_type": "market",
                "thesis": "overlay rebalance into KOSPI ETF position for risk parity",
                "data_sources": ["overlay:kr_kospi_v1"],
                "backtest_ref": "research/kr/results/overlay/kospi_v1_pass_full.json",
                "confidence": 0.72,
                "expires_at": "2026-06-13T15:20:00+09:00",
            }
        ],
    }
    (artifacts / "proposal_batch.json").write_text(
        json.dumps(batch, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_read_playbook_summary_extracts_intraday_section(tmp_path: Path) -> None:
    session = tmp_path / "sess-playbook"
    _write_trading_session(session)

    payload = read_playbook_summary(session)

    assert payload["ok"] is True
    assert "오늘 장중 행동" in payload["summary"]
    assert "Approve only PASS" in payload["summary"]
    assert "Trading Mission" not in payload["summary"]


def test_read_pending_batch_summary_compact(tmp_path: Path) -> None:
    session = tmp_path / "sess-batch"
    _write_trading_session(session)

    payload = read_pending_batch_summary(session)

    assert payload["ok"] is True
    assert payload["mission_id"] == "2026-06-13-premarket"
    assert payload["ingest_ready"] is True
    assert payload["proposal_count"] == 1
    row = payload["proposals"][0]
    assert row["symbol"] == "069500"
    assert len(row["thesis_preview"]) <= 120


def test_read_pending_batch_prefers_delta(tmp_path: Path) -> None:
    session = tmp_path / "sess-delta"
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "proposal_batch.json").write_text(
        json.dumps({"mission_id": "old", "ingest_ready": False, "proposals": []}),
        encoding="utf-8",
    )
    (artifacts / "proposal_delta.json").write_text(
        json.dumps(
            {
                "mission_id": "2026-06-13-delta",
                "ingest_ready": True,
                "proposals": [
                    {
                        "symbol": "005930",
                        "market": "kr",
                        "side": "sell",
                        "quantity": 1,
                        "notional": 50_000,
                        "order_type": "market",
                        "thesis": "signal fade trim",
                        "data_sources": ["signal:fade"],
                        "backtest_ref": "research/kr/results/overlay/kospi_v1_pass_full.json",
                        "confidence": 0.55,
                        "expires_at": "2026-06-13T15:20:00+09:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = read_pending_batch_summary(session)

    assert payload["ok"] is True
    assert payload["source"] == "proposal_delta.json"
    assert payload["mission_id"] == "2026-06-13-delta"
    assert payload["proposals"][0]["symbol"] == "005930"


def test_mcp_tools_with_session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp")
    session = tmp_path / "sess-mcp"
    _write_trading_session(session)
    monkeypatch.setenv("AGENT_LAB_SESSION_FOLDER", str(session))

    from agent_lab.research_mcp_server import get_pending_batch, get_playbook, wisdom_search

    playbook = get_playbook()
    assert playbook["ok"] is True
    assert "장중 행동" in playbook["summary"]

    batch = get_pending_batch()
    assert batch["ok"] is True
    assert batch["proposal_count"] == 1

    monkeypatch.setenv("AGENT_LAB_WISDOM_INDEX", "1")
    (session / "wisdom").mkdir(exist_ok=True)
    (session / "wisdom" / "trading-note.md").write_text(
        "# trading:mission\nblocked proposal due to FAIL ref\n",
        encoding="utf-8",
    )
    hits = wisdom_search("blocked proposal", k=2)
    assert hits["enabled"] is True


def test_mcp_research_card_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp")
    from agent_lab.pipeline_research_read import sync_research_cards
    from agent_lab.research_artifact_card import build_card_from_full_json

    pipeline = tmp_path / "pipeline"
    results = pipeline / "research" / "kr" / "results" / "overlay"
    results.mkdir(parents=True)
    source = results / "kospi_v1_20260601_120000_full.json"
    source.write_text(
        json.dumps(
            {
                "strategy": "kr_kospi_v1",
                "verdict": "PASS",
                "OOS": {"sharpe": 2.4, "mdd": -0.13},
                "fails": [],
            }
        ),
        encoding="utf-8",
    )
    cards_dir = pipeline / "data" / "agentic_trading" / "cards"
    write_card = build_card_from_full_json(source, pipeline)
    cards_dir.mkdir(parents=True, exist_ok=True)
    (cards_dir / "kospi_v1.json").write_text(json.dumps(write_card), encoding="utf-8")
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    from agent_lab.research_mcp_server import (
        get_backtest_card,
        get_strategy_verdict,
        list_wireup_candidates,
    )

    verdict = get_strategy_verdict("kospi_v1")
    assert verdict["ok"] is True
    assert verdict["verdict"] == "PASS"

    card = get_backtest_card("kospi_v1")
    assert card["ok"] is True
    assert card["card"]["eligible_for_proposal"] is True

    sync_research_cards(pipeline, cards_dir=cards_dir)
    listed = list_wireup_candidates(limit=5)
    assert listed["ok"] is True
    assert "kospi_v1" in listed["refs"]


def test_mcp_market_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp")
    pipeline = tmp_path / "pipeline"
    script_dir = pipeline / "scripts" / "spec91"
    script_dir.mkdir(parents=True)
    (script_dir / "quant_control_freshness.py").write_text(
        'import json\nprint(json.dumps({"ok": True, "message": "ok", "rows": []}))\n',
        encoding="utf-8",
    )
    runner = pipeline / "research" / "kr" / "overlay" / "kr_kospi_v1_backtest.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    monkeypatch.setenv("AGENT_LAB_QUOTE_MODE", "mock")

    from agent_lab.research_mcp_server import (
        get_data_freshness,
        get_portfolio_snapshot,
        get_quote,
        list_runnable_backtests,
        run_backtest_refresh,
    )

    quote = get_quote("069500")
    assert quote["ok"] is True

    fresh = get_data_freshness()
    assert fresh["ok"] is True
    assert fresh["freshness"]["ok"] is True

    portfolio = get_portfolio_snapshot()
    assert portfolio["ok"] is True

    runners = list_runnable_backtests()
    assert "kospi_v1" in runners["refs"]

    backtest = run_backtest_refresh("kospi_v1", dry_run=True)
    assert backtest["ok"] is True
    assert backtest["dry_run"] is True
