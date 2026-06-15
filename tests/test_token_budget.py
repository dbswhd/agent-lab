"""Tests for token_budget visibility helpers."""
from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture()
def limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MAX_THREAD_CHARS", "1000")
    monkeypatch.setenv("AGENT_LAB_CONTEXT_WARN_PCT", "50")
    monkeypatch.setenv("AGENT_LAB_CONTEXT_CRITICAL_PCT", "90")


def test_record_run_token_budget_applies_limits(limits: None) -> None:
    from agent_lab.token_budget import record_run_token_budget

    run_meta: dict[str, Any] = {}
    context_log = [
        {"layer_chars": {"total": 600}},
        {"layer_chars": {"total": 200}},
        {"layer_chars": {"total": 300}},
    ]
    turn_meta = {"trim_level": "warn"}

    entry = record_run_token_budget(run_meta, context_log, turn_meta)

    assert entry is not None
    assert entry["last_in"] == 600
    assert entry["last_out"] == 1100
    assert entry["warn"] is True
    assert entry["critical"] is True
    assert entry["cumulative_chars"] == 1100
    assert run_meta["token_budget"] == entry


def test_record_run_token_budget_preserves_existing(limits: None) -> None:
    from agent_lab.token_budget import record_run_token_budget

    run_meta: dict[str, Any] = {"token_budget": {"custom": True}}
    context_log = [{"layer_chars": {"total": 100}}]

    entry = record_run_token_budget(run_meta, context_log)

    assert entry is not None
    assert entry["custom"] is True
    assert entry["last_out"] == 100
