"""Tests for MCP tool contract (allowed read tools, forbidden full-json/execute)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_lab.mcp_tool_contract import (
    FORBIDDEN_TOOLS_GLOBAL,
    QUANT_TRADING_REQUIRED,
    RESEARCH_REQUIRED,
    audit_mcp_contracts,
    collect_tool_names,
    validate_mcp_tool_surface,
)


def test_research_mcp_contract_surface() -> None:
    pytest.importorskip("mcp")

    async def _run() -> None:
        names = await collect_tool_names("agent-lab-research")
        report = validate_mcp_tool_surface(names, server="agent-lab-research")
        assert report["ok"] is True, report["issues"]
        assert RESEARCH_REQUIRED <= set(names)
        assert not (set(names) & FORBIDDEN_TOOLS_GLOBAL)

    asyncio.run(_run())


@pytest.mark.quant
def test_quant_trading_mcp_contract_surface() -> None:
    pytest.importorskip("mcp")

    async def _run() -> None:
        names = await collect_tool_names("quant-trading")
        report = validate_mcp_tool_surface(names, server="quant-trading")
        assert report["ok"] is True, report["issues"]
        assert QUANT_TRADING_REQUIRED <= set(names)
        assert not (set(names) & FORBIDDEN_TOOLS_GLOBAL)

    asyncio.run(_run())


@pytest.mark.quant
def test_mcp_servers_do_not_overlap_exclusive_tools() -> None:
    pytest.importorskip("mcp")

    async def _run() -> None:
        payload = await audit_mcp_contracts()
        assert payload["ok"] is True
        research = set(payload["servers"]["agent-lab-research"]["tools"])
        trading = set(payload["servers"]["quant-trading"]["tools"])
        assert "ingest_proposal_batch" not in trading
        assert "ingest_trading_session" not in trading
        assert "create_trade_proposal" in trading
        assert "get_playbook" in research
        assert "get_playbook" not in trading

    asyncio.run(_run())


@pytest.mark.quant
def test_quant_trading_market_read_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = tmp_path / "pipeline"
    script_dir = pipeline / "scripts" / "spec91"
    script_dir.mkdir(parents=True)
    (script_dir / "quant_control_freshness.py").write_text(
        'import json\nprint(json.dumps({"ok": True, "message": "ok", "rows": []}))\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    monkeypatch.setenv("AGENTIC_QUOTE_MODE", "mock")

    from quant_pipeline.agentic_trading.market_read import (
        get_data_freshness,
        get_kill_switch_status,
        get_quote,
    )

    quote = get_quote("069500")
    assert quote["ok"] is True
    assert quote["symbol"] == "069500"

    fresh = get_data_freshness()
    assert fresh["ok"] is True
    assert fresh["freshness"]["ok"] is True
    assert fresh["freshness"]["trade_allowed"] is True

    kill = get_kill_switch_status()
    assert kill["ok"] is True
    assert kill["kill_switch_enabled"] is False


@pytest.mark.quant
def test_quant_trading_mcp_tools_callable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp")
    pipeline = tmp_path / "pipeline"
    script_dir = pipeline / "scripts" / "spec91"
    script_dir.mkdir(parents=True)
    (script_dir / "quant_control_freshness.py").write_text(
        'import json\nprint(json.dumps({"ok": True, "message": "ok", "rows": []}))\n',
        encoding="utf-8",
    )
    cards_dir = pipeline / "data" / "agentic_trading" / "cards"
    cards_dir.mkdir(parents=True)
    (cards_dir / "demo.json").write_text(
        json.dumps(
            {
                "ref": "demo",
                "verdict": "PASS",
                "eligible_for_proposal": True,
                "oos_sharpe": 1.2,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    from quant_pipeline.quant_trading_mcp_server import (
        get_backtest_card,
        get_data_freshness,
        get_kill_switch_status,
        get_quote,
    )

    assert get_quote("069500")["ok"] is True
    assert get_data_freshness()["freshness"]["ok"] is True
    assert get_kill_switch_status()["trade_allowed"] is True
    card = get_backtest_card("demo")
    assert card["ok"] is True
    assert card["card"]["verdict"] == "PASS"
