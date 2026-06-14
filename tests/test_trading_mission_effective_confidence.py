"""Tests for Trading Mission effective_confidence (agent-lab)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.trading_mission.effective_confidence import (
    batch_context_from_snapshot,
    effective_confidence,
    proposal_needs_human,
)
from agent_lab.trading_mission.export_batch import build_proposal_batch


def test_effective_confidence_uses_card_verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    draft = {
        "confidence": 0.9,
        "backtest_ref": "research/kr/results/overlay/kospi_v1_pass_full.json",
        "notional": 50_000,
        "symbol": "069500",
    }
    snap = {
        "pipeline_root": str(pipeline),
        "trade_allowed": True,
        "freshness": {"ok": True, "blocking": False},
        "portfolio": {"cash": 1_000_000, "equity": 5_000_000, "positions": {}},
    }
    score = effective_confidence(draft, snapshot=snap, pipeline=pipeline)
    assert score < 0.9
    assert score > 0.0


def test_export_batch_embeds_freshness_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = tmp_path / "sess"
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    (session / "plan.md").write_text("## 합의\n- ingest_ready: true\n", encoding="utf-8")
    (artifacts / "market_snapshot.json").write_text(
        json.dumps(
            {
                "trade_allowed": True,
                "freshness": {"ok": True, "blocking": False},
                "portfolio": {"cash": 1_000_000, "equity": 5_000_000, "positions": {}},
                "pipeline_root": str(tmp_path / "pipeline"),
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "proposals_draft.json").write_text(
        json.dumps(
            [
                {
                    "symbol": "069500",
                    "market": "kr",
                    "side": "buy",
                    "notional": 100_000,
                    "backtest_ref": "research/kr/results/good_pass_full.json",
                    "confidence": 0.7,
                }
            ]
        ),
        encoding="utf-8",
    )
    batch = build_proposal_batch(session)
    assert batch["trade_allowed"] is True
    assert batch["freshness_score"] == 1.0
    assert batch["proposals"][0]["effective_confidence_preview"] <= 0.7


def test_needs_human_when_critic_flags() -> None:
    draft = {
        "confidence": 0.9,
        "critic_review": {"needs_human": True, "objections": [], "confidence_cap": 0.9},
    }
    assert proposal_needs_human(draft, effective=0.9) is True


def test_batch_context_from_snapshot_blocking() -> None:
    ctx = batch_context_from_snapshot({"trade_allowed": False, "freshness": {"blocking": True, "ok": False}})
    assert ctx["trade_allowed"] is False
    assert ctx["freshness_score"] == 0.0
