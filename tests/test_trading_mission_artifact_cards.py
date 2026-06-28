"""Tests for Trading Mission artifact card integration."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.quant]

from agent_lab.pipeline_research_read import cards_cache_stale, sync_research_cards_if_stale
from agent_lab.trading_mission.artifact_cards import (
    eligible_cards,
)
from agent_lab.trading_mission.export_batch import build_proposal_batch
from agent_lab.trading_mission.preflight import build_market_snapshot
from agent_lab.trading_mission.verify import check_artifacts
from agent_lab.research.artifact_card import build_card_from_full_json, write_card_cache


def _freshness_pipeline(tmp_path: Path) -> Path:
    pipeline = tmp_path / "pipeline"
    (pipeline / "scripts" / "spec91").mkdir(parents=True)
    (pipeline / "scripts" / "spec91" / "quant_control_freshness.py").write_text(
        'import json\nprint(json.dumps({"ok": True, "message": "ok", "rows": []}))\n',
        encoding="utf-8",
    )
    return pipeline


def _pass_full(pipeline: Path, ref: str = "demo_pass") -> Path:
    results = pipeline / "research" / "kr" / "results" / "overlay"
    results.mkdir(parents=True, exist_ok=True)
    path = results / f"{ref}_20260601_120000_full.json"
    path.write_text(
        json.dumps(
            {
                "strategy": ref,
                "verdict": "PASS",
                "OOS": {"sharpe": 1.5, "mdd": -0.1},
                "fails": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def _fail_full(pipeline: Path, ref: str = "demo_fail") -> Path:
    results = pipeline / "research" / "kr" / "results" / "value"
    results.mkdir(parents=True, exist_ok=True)
    path = results / f"{ref}_20260601_120000_full.json"
    path.write_text(
        json.dumps(
            {
                "strategy": ref,
                "is_winner": {"verdict": "FAIL", "fails": ["oos"], "OOS": {"sharpe": 0.1}},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_eligible_cards_filters_fail():
    cards = [
        {"ref": "a", "verdict": "PASS", "eligible_for_proposal": True, "oos_sharpe": 2},
        {"ref": "b", "verdict": "FAIL", "eligible_for_proposal": False, "oos_sharpe": 1},
    ]
    out = eligible_cards(cards)
    assert len(out) == 1
    assert out[0]["ref"] == "a"


def test_cards_cache_stale_detects_new_full_json(tmp_path: Path):
    import os

    pipeline = _freshness_pipeline(tmp_path)
    source = _pass_full(pipeline)
    cards_dir = pipeline / "data" / "agentic_trading" / "cards"
    card = build_card_from_full_json(source, pipeline)
    write_card_cache(cards_dir, card)
    assert cards_cache_stale(pipeline, cards_dir=cards_dir) is False

    source.write_text(
        json.dumps({"strategy": "demo_pass", "verdict": "PASS", "OOS": {"sharpe": 9}}),
        encoding="utf-8",
    )
    # cards_cache_stale uses a 1s buffer vs cache mtime
    os.utime(source, (time.time() + 2, time.time() + 2))
    assert cards_cache_stale(pipeline, cards_dir=cards_dir) is True


def test_sync_if_stale_skips_fresh_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = _freshness_pipeline(tmp_path)
    source = _pass_full(pipeline)
    cards_dir = pipeline / "data" / "agentic_trading" / "cards"
    write_card_cache(cards_dir, build_card_from_full_json(source, pipeline))
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    report = sync_research_cards_if_stale(pipeline, cards_dir=cards_dir)
    assert report.get("skipped") is True


def test_preflight_snapshot_includes_card_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = _freshness_pipeline(tmp_path)
    _pass_full(pipeline)
    _fail_full(pipeline)
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    snap = build_market_snapshot(pipeline, sync_cards=True)

    assert snap["strategy_cards_count"] >= 2
    assert snap["eligible_cards_count"] >= 1
    assert all(c.get("eligible_for_proposal") for c in snap["eligible_cards"])
    assert "demo_fail" in (snap.get("ineligible_refs") or [])
    assert isinstance(snap.get("strategy_card_index"), list)


def test_export_batch_drops_fail_proposals(tmp_path: Path):
    session = tmp_path / "sess"
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    pipeline = tmp_path / "pipeline"
    cards_dir = pipeline / "data" / "agentic_trading" / "cards"
    cards_dir.mkdir(parents=True)
    write_card_cache(
        cards_dir,
        {
            "ref": "bad_20260601",
            "verdict": "FAIL",
            "eligible_for_proposal": False,
            "source_file": "research/kr/results/bad_20260601_full.json",
        },
    )
    (artifacts / "market_snapshot.json").write_text(
        json.dumps(
            {
                "trade_allowed": True,
                "pipeline_root": str(pipeline),
                "eligible_cards": [],
            }
        ),
        encoding="utf-8",
    )
    (session / "plan.md").write_text("## 합의\n- ingest_ready: true\n", encoding="utf-8")
    (artifacts / "proposals_draft.json").write_text(
        json.dumps(
            [
                {
                    "symbol": "069500",
                    "market": "kr",
                    "side": "buy",
                    "notional": 100000,
                    "backtest_ref": "research/kr/results/bad_20260601_full.json",
                },
                {
                    "symbol": "069500",
                    "market": "kr",
                    "side": "buy",
                    "notional": 100000,
                    "backtest_ref": "research/kr/results/good_20260601_full.json",
                },
            ]
        ),
        encoding="utf-8",
    )
    write_card_cache(
        cards_dir,
        {
            "ref": "good_20260601",
            "verdict": "PASS",
            "eligible_for_proposal": True,
            "source_file": "research/kr/results/good_20260601_full.json",
        },
    )

    batch = build_proposal_batch(session)
    assert batch["dropped_fail_refs"] == 1
    assert len(batch["proposals"]) == 1


def test_verify_cards_check(tmp_path: Path):
    session = tmp_path / "sess"
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "market_snapshot.json").write_text(
        json.dumps(
            {
                "pipeline_root": str(tmp_path / "pipeline"),
                "eligible_cards": [{"ref": "x", "verdict": "PASS"}],
                "strategy_card_index": [{"ref": "x", "verdict": "PASS", "eligible_for_proposal": True}],
                "ineligible_refs": ["y"],
                "cards_sync": {"skipped": True, "reason": "cache fresh"},
            }
        ),
        encoding="utf-8",
    )
    cards_dir = tmp_path / "pipeline" / "data" / "agentic_trading" / "cards"
    cards_dir.mkdir(parents=True)
    (cards_dir / "x.json").write_text("{}", encoding="utf-8")

    report = check_artifacts(session, check="cards")
    assert report["ok"] is True
    names = [c["name"] for c in report["checks"]]
    assert "strategy_card_index present" in names
