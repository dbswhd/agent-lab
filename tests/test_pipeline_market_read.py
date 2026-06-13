"""Tests for pipeline market read + backtest delegate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.backtest_runner_delegate import run_backtest_delegate
from agent_lab.pipeline_market_read import (
    get_data_freshness,
    get_portfolio_snapshot,
    get_quote,
    read_overlay_signals,
    run_data_freshness,
)


def _pipeline(tmp_path: Path) -> Path:
    root = tmp_path / "pipeline"
    root.mkdir()
    return root


def test_get_quote_mock_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_QUOTE_MODE", "mock")
    payload = get_quote("069500")
    assert payload["ok"] is True
    assert payload["symbol"] == "069500"
    assert len(payload) <= 11
    assert "price" in payload


def test_get_quote_unknown_symbol_mock(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_QUOTE_MODE", "mock")
    payload = get_quote("999999")
    assert payload["ok"] is True
    assert payload["source"] == "mock_default"


def test_run_data_freshness_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = _pipeline(tmp_path)
    script_dir = pipeline / "scripts" / "spec91"
    script_dir.mkdir(parents=True)
    (script_dir / "quant_control_freshness.py").write_text(
        'import json\nprint(json.dumps({"ok": True, "message": "ok", "rows": [{"id": "kor"}]}))\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    block = run_data_freshness(pipeline)
    assert block["ok"] is True
    assert block["blocking"] is False
    assert block["trade_allowed"] is True
    assert len(block["rows"]) <= 8


def test_get_data_freshness_wrapper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = _pipeline(tmp_path)
    script_dir = pipeline / "scripts" / "spec91"
    script_dir.mkdir(parents=True)
    (script_dir / "quant_control_freshness.py").write_text(
        'import json\nprint(json.dumps({"ok": False, "message": "stale", "rows": []}))\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    payload = get_data_freshness(pipeline=pipeline)
    assert payload["ok"] is True
    assert payload["freshness"]["blocking"] is True


def test_portfolio_mock_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = _pipeline(tmp_path)
    mock = pipeline / "data" / "agentic_trading" / "mock_portfolio.json"
    mock.parent.mkdir(parents=True)
    mock.write_text(
        json.dumps({"cash": 2_000_000, "equity": 8_000_000, "positions": {"069500": 10}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    payload = get_portfolio_snapshot(pipeline=pipeline)
    assert payload["ok"] is True
    assert payload["cash"] == 2_000_000
    assert payload["positions"]["069500"] == 10


def test_overlay_signals_reads_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = _pipeline(tmp_path)
    state = pipeline / "data" / "kr_kospi_v1" / "holdings_state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"position": "bull"}), encoding="utf-8")
    flag = pipeline / "logs" / "kr_kospi_v1" / "ACTION_REQUIRED.flag"
    flag.parent.mkdir(parents=True)
    flag.write_text("", encoding="utf-8")
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    signals = read_overlay_signals(pipeline)
    assert signals["kr_kospi_v1"]["position"] == "bull"
    assert signals["kr_kospi_v1"]["flag"] == "ACTION_REQUIRED.flag"


def test_backtest_delegate_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = _pipeline(tmp_path)
    runner = pipeline / "research" / "kr" / "overlay" / "kr_kospi_v1_backtest.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    report = run_backtest_delegate("kospi_v1", pipeline=pipeline, dry_run=True)
    assert report["ok"] is True
    assert report["dry_run"] is True
    assert "kr_kospi_v1_backtest.py" in report["script"]


def test_backtest_delegate_unknown_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipeline = _pipeline(tmp_path)
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    report = run_backtest_delegate("unknown_strategy", pipeline=pipeline)
    assert report["ok"] is False
