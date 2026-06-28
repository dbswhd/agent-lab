"""Parity: agent-lab delegates match quant-agentic-trading SSoT."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.extensions.quant_runtime import load_quant_module
from agent_lab.research.artifact_card import build_card_from_full_json
from agent_lab.trading_mission.effective_confidence import effective_confidence


@pytest.fixture
def quant_confidence():
    mod = load_quant_module("quant_pipeline.agentic_trading.confidence")
    if mod is None:
        pytest.skip("quant-agentic-trading src not on PYTHONPATH")
    return mod


def test_card_builder_matches_quant_ssot(tmp_path: Path) -> None:
    mod = load_quant_module("quant_pipeline.agentic_trading.card_builder")
    if mod is None:
        pytest.skip("quant-agentic-trading src not on PYTHONPATH")

    pipeline = tmp_path / "pipeline"
    results = pipeline / "research" / "kr" / "results" / "overlay"
    results.mkdir(parents=True)
    source = results / "kospi_v1_20260601_234048_full.json"
    source.write_text(
        json.dumps(
            {
                "strategy": "kospi_v1",
                "verdict": "PASS",
                "OOS": {"sharpe": 1.2, "mdd": -0.1},
                "params": {"score_mode": "z"},
            }
        ),
        encoding="utf-8",
    )

    local = build_card_from_full_json(source, pipeline)
    remote = mod.build_card_from_full_json(source, pipeline)
    assert local["ref"] == remote["ref"] == "kospi_v1"
    assert local["verdict"] == remote["verdict"] == "PASS"
    assert local["eligible_for_proposal"] is True


def test_effective_confidence_matches_quant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    quant_confidence,
) -> None:
    pipeline = tmp_path / "pipeline"
    cards = pipeline / "data" / "agentic_trading" / "cards"
    cards.mkdir(parents=True)
    (cards / "kospi_v1.json").write_text(
        json.dumps(
            {
                "ref": "kospi_v1",
                "verdict": "PASS",
                "eligible_for_proposal": True,
                "oos_sharpe": 1.1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    draft = {
        "confidence": 0.9,
        "backtest_ref": "kospi_v1",
        "symbol": "069500",
        "notional": 100_000,
    }
    snap = {
        "trade_allowed": True,
        "freshness": {"ok": True, "blocking": False},
        "portfolio": {"cash": 2_000_000, "equity": 5_000_000, "positions": {}},
    }

    lab_score = effective_confidence(draft, snapshot=snap, pipeline=pipeline)
    quant_score = quant_confidence.effective_confidence(draft, snapshot=snap, pipeline=pipeline)
    assert lab_score == quant_score
