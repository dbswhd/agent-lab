"""Agent availability — usage-limit pauses and turn filtering."""

from __future__ import annotations

import time

from agent_lab.agent.availability import (
    agent_pause_until,
    filter_agents_for_turn,
    is_usage_limit_error,
    record_usage_limit_pause,
)
from agent_lab.agents.registry import AgentId


def test_is_usage_limit_error() -> None:
    assert is_usage_limit_error("ERROR: usage limit reached")
    assert is_usage_limit_error("429 rate limit")
    assert not is_usage_limit_error("connection refused")


def test_record_and_filter_paused_agent() -> None:
    run_meta: dict = {"_session_folder": "/tmp/x"}
    record_usage_limit_pause("claude", run_meta=run_meta, error="usage limit", now=1000.0)
    assert agent_pause_until(run_meta, "claude", now=1001.0) == 1000.0 + 15 * 60
    filtered = filter_agents_for_turn(
        ["claude", "codex"],  # type: ignore[list-item]
        run_meta=run_meta,
        now=1001.0,
    )
    assert filtered == ["codex"]


def test_expired_pause_rejoins() -> None:
    run_meta: dict = {}
    record_usage_limit_pause("claude", run_meta=run_meta, error="quota", now=1000.0, pause_seconds=60.0)
    assert agent_pause_until(run_meta, "claude", now=1100.0) is None
    filtered = filter_agents_for_turn(
        ["claude"],  # type: ignore[list-item]
        run_meta=run_meta,
        now=1100.0,
    )
    assert filtered == ["claude"]
