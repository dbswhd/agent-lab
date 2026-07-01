"""Tests for the real token/USD cost ledger (G1 economics)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_lab.cost_ledger import (
    AgentUsage,
    budget_status,
    chars_to_tokens,
    estimate_usage_from_text,
    persist_cost_ledger,
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
    from agent_lab.claude.cli import _emit_claude_usage

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


def test_claude_cli_emits_estimated_usage_without_provider_signal() -> None:
    from agent_lab.claude.cli import _emit_claude_usage

    events: list[tuple[str, dict[str, Any]]] = []
    _emit_claude_usage(
        {"type": "result", "result": "hello world"},
        lambda kind, data: events.append((kind, data)),
        result_text="hello world",
    )
    assert len(events) == 1
    kind, payload = events[0]
    assert kind == "usage"
    usage = usage_from_bridge(payload)
    assert usage is not None
    assert usage.source == "estimated"
    assert usage.tokens_out >= 1


def test_estimate_usage_from_text() -> None:
    est = estimate_usage_from_text(input_chars=3500, output_chars=700, model="claude-opus")
    assert est.tokens_in == chars_to_tokens(3500)
    assert est.tokens_out == chars_to_tokens(700)
    assert est.source == "estimated"
    assert est.tokens_in == 1750  # default 2.0 chars/token


def test_chars_to_tokens_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHARS_PER_TOKEN", "3.5")
    assert chars_to_tokens(3500) == 1000
    monkeypatch.delenv("AGENT_LAB_CHARS_PER_TOKEN", raising=False)
    assert chars_to_tokens(3500) == 1750


def test_record_tracks_provider_vs_estimated_calls() -> None:
    run_meta: dict[str, Any] = {}
    record_agent_usage(
        run_meta,
        "claude",
        AgentUsage(tokens_in=100, tokens_out=50, source="estimated"),
    )
    record_agent_usage(
        run_meta,
        "claude",
        usage_from_bridge({"input_tokens": 200, "output_tokens": 80}),
    )
    entry = run_meta["cost_ledger"]["by_agent"]["claude"]
    assert entry["estimated_calls"] == 1
    assert entry["provider_calls"] == 1


def test_persist_cost_ledger_writes_run_json(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}\n", encoding="utf-8")
    run_meta: dict[str, Any] = {
        "cost_ledger": {
            "by_agent": {"claude": {"calls": 1, "tokens_in": 10, "tokens_out": 5, "usd": 0.01}},
            "cumulative": {"tokens_in": 10, "tokens_out": 5, "usd": 0.01},
        }
    }
    persist_cost_ledger(folder, run_meta)
    import json

    saved = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert saved["cost_ledger"]["cumulative"]["tokens_in"] == 10


def test_claude_cli_usage_noop_without_signal() -> None:
    from agent_lab.claude.cli import _emit_claude_usage

    events: list[Any] = []
    _emit_claude_usage({"type": "result"}, lambda k, d: events.append((k, d)))
    assert events == []
