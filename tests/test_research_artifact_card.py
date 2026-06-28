"""Tests for ResearchArtifactCard build + pipeline research read."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.quant]

from agent_lab.pipeline_research_read import (
    get_backtest_card,
    get_strategy_verdict,
    list_wireup_candidates,
    sync_research_cards,
)
from agent_lab.research.artifact_card import (
    build_card_from_full_json,
    slug_from_full_path,
)


def _write_pass_full(results: Path, name: str = "demo_pass") -> Path:
    path = results / "overlay" / f"{name}_20260601_120000_full.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "strategy": "kr_kospi_v1",
                "name": "demo overlay",
                "params": {"VIX_THR": 22.0, "SIZE_5OF5": 1.0},
                "OOS": {"sharpe": 2.1, "mdd": -0.12, "cagr": 0.4},
                "verdict": "PASS",
                "fails": [],
                "runtag": "20260601_120000",
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_fail_full(results: Path) -> Path:
    path = results / "value_up" / "demo_fail_20260601_120000_full.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "strategy": "demo_fail",
                "meta_verdict": "FAIL",
                "is_winner": {
                    "verdict": "FAIL",
                    "fails": ["oos sharpe below threshold"],
                    "params": {"top_n": 10},
                    "OOS": {"sharpe": 0.2, "mdd": -0.3},
                },
                "runtag": "20260601_120000",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_slug_from_full_path():
    assert slug_from_full_path(Path("kospi_v1_20260601_234048_full.json")) == "kospi_v1"


def test_build_card_pass_eligible(tmp_path: Path):
    pipeline = tmp_path / "pipeline"
    results = pipeline / "research" / "kr" / "results"
    source = _write_pass_full(results)

    card = build_card_from_full_json(source, pipeline)

    assert card["ref"] == "demo_pass"
    assert card["verdict"] == "PASS"
    assert card["eligible_for_proposal"] is True
    assert card["oos_sharpe"] == 2.1
    from agent_lab.research.artifact_card import CARD_MAX_BYTES

    assert card["size_bytes"] <= CARD_MAX_BYTES


def test_build_card_fail_not_eligible(tmp_path: Path):
    pipeline = tmp_path / "pipeline"
    results = pipeline / "research" / "kr" / "results"
    source = _write_fail_full(results)

    card = build_card_from_full_json(source, pipeline)

    assert card["verdict"] == "FAIL"
    assert card["eligible_for_proposal"] is False
    assert card["fails"]


def test_sync_writes_pass_and_fail_cards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = tmp_path / "pipeline"
    results = pipeline / "research" / "kr" / "results"
    _write_pass_full(results)
    _write_fail_full(results)
    cards_dir = pipeline / "data" / "agentic_trading" / "cards"
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    report = sync_research_cards(pipeline, cards_dir=cards_dir, include_ineligible=True)

    assert report["written"] == 2
    assert (cards_dir / "demo_pass.json").is_file()
    assert (cards_dir / "demo_fail.json").is_file()
    fail_card = json.loads((cards_dir / "demo_fail.json").read_text(encoding="utf-8"))
    assert fail_card["eligible_for_proposal"] is False


def test_get_strategy_verdict_and_wireup_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = tmp_path / "pipeline"
    results = pipeline / "research" / "kr" / "results"
    _write_pass_full(results)
    _write_fail_full(results)
    cards_dir = pipeline / "data" / "agentic_trading" / "cards"
    sync_research_cards(pipeline, cards_dir=cards_dir)
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    verdict = get_strategy_verdict("demo_pass", pipeline=pipeline)
    assert verdict["ok"] is True
    assert verdict["verdict"] == "PASS"
    assert verdict["eligible_for_proposal"] is True

    fail = get_strategy_verdict("demo_fail", pipeline=pipeline)
    assert fail["eligible_for_proposal"] is False

    listed = list_wireup_candidates(pipeline=pipeline, limit=10)
    assert listed["ok"] is True
    assert listed["count"] == 1
    assert listed["refs"] == ["demo_pass"]


def test_get_backtest_card_from_source_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = tmp_path / "pipeline"
    _write_pass_full(pipeline / "research" / "kr" / "results")
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    payload = get_backtest_card(
        "research/kr/results/overlay/demo_pass_20260601_120000_full.json",
        pipeline=pipeline,
        prefer_cache=False,
    )
    assert payload["ok"] is True
    assert payload["card"]["ref"] == "demo_pass"
