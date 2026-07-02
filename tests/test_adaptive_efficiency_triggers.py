"""Tests for proactive adaptive efficiency triggers."""

from __future__ import annotations

from agent_lab.room.turn_flow_support import (
    _maybe_enable_adaptive_efficiency,
    ensure_adaptive_efficiency_for_turn,
)


class _Events:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def __call__(self, name: str, data: dict) -> None:
        self.events.append((name, data))


def test_ensure_adaptive_efficiency_on_long_session():
    run_meta: dict = {}
    ensure_adaptive_efficiency_for_turn(run_meta, human_turn=5)
    assert run_meta["adaptive_efficiency"] is True


def test_ensure_adaptive_efficiency_on_critical_budget():
    run_meta: dict = {"token_budget": {"critical": True}}
    ensure_adaptive_efficiency_for_turn(run_meta, human_turn=1)
    assert run_meta["adaptive_efficiency"] is True


def test_maybe_enable_on_warn_not_only_over():
    run_meta: dict = {}
    ev = _Events()
    _maybe_enable_adaptive_efficiency(
        run_meta,
        ev,
        {"warn": True, "over": False, "cumulative": 1.0},
    )
    assert run_meta["adaptive_efficiency"] is True
    assert any(name == "efficiency_auto_enabled" for name, _ in ev.events)
