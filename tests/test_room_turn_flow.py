"""Unit tests for helpers in room_turn_flow.py."""

from __future__ import annotations

import pytest

import agent_lab.room.turn_flow as rtf


# ---------------------------------------------------------------------------
# _session_hard_cap_enabled
# ---------------------------------------------------------------------------


def test_session_hard_cap_disabled_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGENT_LAB_SESSION_HARD_CAP", raising=False)
    assert rtf._session_hard_cap_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "True", "yes", "on", "ON"])
def test_session_hard_cap_enabled_truthy(monkeypatch: pytest.MonkeyPatch, value: str):
    monkeypatch.setenv("AGENT_LAB_SESSION_HARD_CAP", value)
    assert rtf._session_hard_cap_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
def test_session_hard_cap_disabled_falsy(monkeypatch: pytest.MonkeyPatch, value: str):
    monkeypatch.setenv("AGENT_LAB_SESSION_HARD_CAP", value)
    assert rtf._session_hard_cap_enabled() is False


# ---------------------------------------------------------------------------
# _resolve_stage_routing — flag OFF parity
# ---------------------------------------------------------------------------


def test_resolve_stage_routing_flag_off_returns_unchanged(monkeypatch: pytest.MonkeyPatch):
    """With AGENT_LAB_STAGE_ROUTING off, consensus_mode is returned unchanged."""
    monkeypatch.delenv("AGENT_LAB_STAGE_ROUTING", raising=False)
    run_meta: dict = {}
    assert rtf._resolve_stage_routing(run_meta, turn_profile=None, consensus_mode=True, folder=None) is True
    assert rtf._resolve_stage_routing(run_meta, turn_profile=None, consensus_mode=False, folder=None) is False


# ---------------------------------------------------------------------------
# _emit_budget_status
# ---------------------------------------------------------------------------


def test_emit_budget_status_no_op_without_on_event():
    run_meta = {"cost_ledger": {}}
    # Should not raise even without on_event
    rtf._emit_budget_status(run_meta, None)


def test_emit_budget_status_emits_event(monkeypatch: pytest.MonkeyPatch):
    from agent_lab import cost_ledger

    monkeypatch.setattr(
        cost_ledger,
        "session_budget_action",
        lambda _run: {
            "warn": False,
            "over": False,
            "budget_set": False,
            "cumulative": 0.0,
        },
    )
    events: list[tuple[str, object]] = []
    run_meta: dict = {}
    rtf._emit_budget_status(run_meta, lambda name, data: events.append((name, data)))
    assert any(name == "budget_status" for name, _ in events)
    assert "budget_status" in run_meta


def test_emit_budget_status_sets_adaptive_efficiency_when_over(monkeypatch: pytest.MonkeyPatch):
    from agent_lab import cost_ledger

    monkeypatch.setattr(
        cost_ledger,
        "session_budget_action",
        lambda _run: {
            "warn": True,
            "over": True,
            "budget_set": True,
            "cumulative": 999.0,
            "usd_limit": 10.0,
            "token_limit": None,
        },
    )
    events: list[tuple[str, object]] = []
    run_meta: dict = {}
    rtf._emit_budget_status(run_meta, lambda name, data: events.append((name, data)))
    assert run_meta.get("adaptive_efficiency") is True
    assert any(name == "efficiency_auto_enabled" for name, _ in events)


def test_emit_budget_status_does_not_repeat_adaptive_efficiency(monkeypatch: pytest.MonkeyPatch):
    from agent_lab import cost_ledger

    monkeypatch.setattr(
        cost_ledger,
        "session_budget_action",
        lambda _run: {"warn": True, "over": True, "budget_set": True, "cumulative": 999.0},
    )
    events: list[tuple[str, object]] = []
    run_meta: dict = {"adaptive_efficiency": True}
    rtf._emit_budget_status(run_meta, lambda name, data: events.append((name, data)))
    # efficiency_auto_enabled should NOT be emitted again
    assert not any(name == "efficiency_auto_enabled" for name, _ in events)


# ---------------------------------------------------------------------------
# _emit_divergence_options
# ---------------------------------------------------------------------------


def test_emit_divergence_options_no_op_non_divergence_profile():
    events: list = []
    run_meta = {"turn_profile": "discuss"}
    rtf._emit_divergence_options(run_meta, ["option A", "option B"], lambda n, d: events.append(n), False)
    assert events == []


def test_emit_divergence_options_no_op_when_cancelled():
    events: list = []
    run_meta = {"turn_profile": "diverge"}
    rtf._emit_divergence_options(run_meta, ["option A"], lambda n, d: events.append(n), cancelled=True)
    assert events == []


def test_emit_divergence_options_no_op_no_replies():
    events: list = []
    run_meta = {"turn_profile": "diverge"}
    rtf._emit_divergence_options(run_meta, [], lambda n, d: events.append(n), cancelled=False)
    assert events == []
