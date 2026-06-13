"""Agent-lab core must not require quant sibling repos."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.extensions.quant_trading import (
    agentic_trading_available,
    optional_agentic_src,
    optional_pipeline_root,
    quant_pipeline_available,
)
from agent_lab.pipeline_market_read import get_data_freshness, get_quote
from agent_lab.session_setup import TRADING_TEMPLATE_IDS, list_session_templates


def test_core_mock_quote_without_pipeline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("QUANT_PIPELINE_ROOT", raising=False)
    monkeypatch.setenv("AGENT_LAB_QUOTE_MODE", "mock")
    monkeypatch.setattr(
        "agent_lab.pipeline_market_read.optional_pipeline_root",
        lambda: None,
    )
    payload = get_quote("069500")
    assert payload["ok"] is True
    assert payload["symbol"] == "069500"


def test_freshness_unavailable_without_pipeline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "agent_lab.pipeline_market_read.optional_pipeline_root",
        lambda: None,
    )
    payload = get_data_freshness()
    assert payload["ok"] is False
    assert payload["extension"] == "quant_pipeline"


def test_trading_templates_hidden_without_pipeline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "agent_lab.extensions.quant_trading.quant_pipeline_available",
        lambda: False,
    )
    ids = {t["id"] for t in list_session_templates()}
    assert "general" in ids
    assert TRADING_TEMPLATE_IDS.isdisjoint(ids)


def test_trading_templates_visible_with_pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pipeline = tmp_path / "pipeline"
    pipeline.mkdir()
    monkeypatch.setattr(
        "agent_lab.extensions.quant_trading.optional_pipeline_root",
        lambda: pipeline.resolve(),
    )
    monkeypatch.setattr(
        "agent_lab.extensions.quant_trading.quant_pipeline_available",
        lambda: True,
    )
    ids = {t["id"] for t in list_session_templates()}
    assert TRADING_TEMPLATE_IDS.issubset(ids)


def test_optional_roots_no_crash_without_siblings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "config.toml").write_text("[paths]\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("QUANT_PIPELINE_ROOT", raising=False)
    monkeypatch.delenv("AGENTIC_QUANT_PIPELINE_SRC", raising=False)
    monkeypatch.setattr(
        "agent_lab.extensions.quant_trading._home",
        lambda: tmp_path,
    )
    assert optional_pipeline_root() is None
    assert quant_pipeline_available() is False
    assert optional_agentic_src() is None
    assert agentic_trading_available() is False
