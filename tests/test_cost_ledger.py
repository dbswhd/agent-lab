"""Tests for the real token/USD cost ledger (G1 economics)."""

from __future__ import annotations

from typing import Any

import pytest

from agent_lab.cost_ledger import (
    AgentUsage,
    budget_status,
    record_agent_usage,
    usage_from_bridge,
)


def test_usage_from_bridge_anthropic_shape() -> None:
    usage = usage_from_bridge(
        {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_input_tokens": 800,
            "cache_creation_input_tokens": 50,
            "total_cost_usd": 0.05,
            "model": "opus",
        }
    )
    assert usage is not None
    assert usage.tokens_in == 1000
    assert usage.tokens_out == 200
    assert usage.cache_read == 800
    assert usage.cache_creation == 50
    assert usage.usd == 0.05


def test_usage_from_bridge_empty_returns_none() -> None:
    assert usage_from_bridge({}) is None
    assert usage_from_bridge(None) is None
    assert usage_from_bridge({"input_tokens": 0, "output_tokens": 0}) is None


def test_resolved_usd_estimates_when_no_provider_cost() -> None:
    # No usd reported → estimate via pricing table (gpt-5.x tier).
    usage = AgentUsage(tokens_in=500, tokens_out=100, model="gpt-5.5")
    assert usage.usd is None
    assert usage.resolved_usd() == pytest.approx(0.001625, rel=1e-6)


def test_record_accumulates_per_agent_and_cumulative() -> None:
    run_meta: dict[str, Any] = {}
    record_agent_usage(
        run_meta,
        "claude",
        usage_from_bridge(
            {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 800, "total_cost_usd": 0.05}
        ),
        turn=1,
    )
    record_agent_usage(
        run_meta,
        "claude",
        usage_from_bridge({"input_tokens": 400, "output_tokens": 100, "total_cost_usd": 0.02}),
        turn=2,
    )
    ledger = run_meta["cost_ledger"]
    claude = ledger["by_agent"]["claude"]
    assert claude["calls"] == 2
    assert claude["tokens_in"] == 1400
    assert claude["usd"] == pytest.approx(0.07)
    assert ledger["cumulative"]["usd"] == pytest.approx(0.07)
    assert ledger["cache_hit_rate"] == pytest.approx(800 / 1400, rel=1e-3)
    assert ledger["updated_at_turn"] == 2


def test_record_noop_on_missing() -> None:
    assert record_agent_usage(None, "claude", AgentUsage(tokens_in=1)) is None
    run_meta: dict[str, Any] = {}
    assert record_agent_usage(run_meta, "claude", None) is None
    assert "cost_ledger" not in run_meta


def test_budget_status_unlimited_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MISSION_BUDGET_USD", raising=False)
    status = budget_status({"cost_ledger": {"cumulative": {"usd": 999.0}}})
    assert status["limit_usd"] is None
    assert status["over"] is False
    assert status["spent_usd"] == 999.0


def test_budget_status_over_and_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_BUDGET_USD", "0.10")
    monkeypatch.setenv("AGENT_LAB_BUDGET_WARN_PCT", "80")
    under = budget_status({"cost_ledger": {"cumulative": {"usd": 0.05}}})
    assert under["over"] is False and under["warn"] is False
    warning = budget_status({"cost_ledger": {"cumulative": {"usd": 0.085}}})
    assert warning["over"] is False and warning["warn"] is True
    over = budget_status({"cost_ledger": {"cumulative": {"usd": 0.12}}})
    assert over["over"] is True and over["warn"] is True


def test_budget_status_invalid_limit_is_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_BUDGET_USD", "not-a-number")
    assert budget_status({})["limit_usd"] is None
    monkeypatch.setenv("AGENT_LAB_MISSION_BUDGET_USD", "0")
    assert budget_status({})["limit_usd"] is None


def test_claude_cli_emits_usage_from_result_event() -> None:
    from agent_lab.claude_cli import _emit_claude_usage

    events: list[tuple[str, dict[str, Any]]] = []
    result_event = {
        "type": "result",
        "result": "done",
        "usage": {
            "input_tokens": 1200,
            "output_tokens": 340,
            "cache_read_input_tokens": 900,
            "cache_creation_input_tokens": 0,
        },
        "total_cost_usd": 0.061,
        "model": "claude-opus-4-8",
    }
    _emit_claude_usage(result_event, lambda kind, data: events.append((kind, data)))
    assert len(events) == 1
    kind, payload = events[0]
    assert kind == "usage"
    usage = usage_from_bridge(payload)
    assert usage is not None
    assert usage.tokens_in == 1200
    assert usage.cache_read == 900
    assert usage.usd == pytest.approx(0.061)


def test_claude_cli_usage_noop_without_signal() -> None:
    from agent_lab.claude_cli import _emit_claude_usage

    events: list[Any] = []
    _emit_claude_usage({"type": "result", "result": "x"}, lambda k, d: events.append((k, d)))
    assert events == []
