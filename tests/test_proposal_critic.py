"""Tests for proposal_critic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.proposal_critic import (
    apply_confidence_cap,
    review_proposal_thesis,
)


def _write_pass_card(pipeline: Path, ref: str = "demo_pass") -> None:
    cards = pipeline / "data" / "agentic_trading" / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    (cards / f"{ref}.json").write_text(
        json.dumps(
            {
                "ref": ref,
                "verdict": "PASS",
                "eligible_for_proposal": True,
                "oos_sharpe": 2.0,
                "fails": [],
                "source_file": f"research/kr/results/overlay/{ref}_full.json",
            }
        ),
        encoding="utf-8",
    )


def _write_fail_card(pipeline: Path, ref: str = "demo_fail") -> None:
    cards = pipeline / "data" / "agentic_trading" / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    (cards / f"{ref}.json").write_text(
        json.dumps(
            {
                "ref": ref,
                "verdict": "FAIL",
                "eligible_for_proposal": False,
                "oos_sharpe": 0.1,
                "fails": ["oos sharpe below threshold"],
                "source_file": f"research/kr/results/value_up/{ref}_full.json",
            }
        ),
        encoding="utf-8",
    )


def test_review_pass_thesis_high_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = tmp_path / "pipeline"
    _write_pass_card(pipeline, "kospi_v1")
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    review = review_proposal_thesis(
        "Overlay kr_kospi_v1 rebalance into 069500 with 100k notional after PASS OOS sharpe 2.0",
        "kospi_v1",
        {"ok": True, "symbol": "069500", "price": 35120},
        symbol="069500",
        agent_confidence=0.72,
    )

    assert review["ok"] is True
    assert review["confidence_cap"] > 0.5
    assert review["verdict"]["verdict"] == "PASS"
    assert not review["objections"] or review["confidence_cap"] > 0


def test_review_fail_ref_zero_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = tmp_path / "pipeline"
    _write_fail_card(pipeline)
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    review = review_proposal_thesis("buy anyway", "demo_fail", agent_confidence=0.8)

    assert review["confidence_cap"] == 0.0
    assert review["needs_human"] is True
    assert any("FAIL" in o or "fail" in o.lower() for o in review["objections"])


def test_review_blocked_phrase(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = tmp_path / "pipeline"
    _write_pass_card(pipeline)
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    review = review_proposal_thesis(
        "bypass risk and place this live order with 100k",
        "demo_pass",
        agent_confidence=0.9,
    )

    assert review["needs_human"] is True
    assert any("blocked" in o for o in review["objections"])


def test_apply_confidence_cap():
    review = {"confidence_cap": 0.55}
    assert apply_confidence_cap(0.72, review) == 0.55
    assert apply_confidence_cap(0.4, review) == 0.4


def test_mcp_review_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp")
    pipeline = tmp_path / "pipeline"
    _write_pass_card(pipeline, "kospi_v1")
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    from agent_lab.research_mcp_server import review_proposal_thesis as mcp_review

    payload = mcp_review(
        thesis="Rebalance 069500 100k on overlay PASS signal",
        ref="kospi_v1",
        quote_json='{"ok": true, "symbol": "069500", "price": 35000}',
        symbol="069500",
        agent_confidence=0.7,
    )
    assert payload["ok"] is True
    assert "confidence_cap" in payload
