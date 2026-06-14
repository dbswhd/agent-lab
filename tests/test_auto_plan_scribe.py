"""Auto plan scribe after every turn (all modes)."""

from __future__ import annotations

from unittest.mock import patch

from agent_lab.room import (
    _apply_scribe_after_turn,
    _should_scribe_plan_after_turn,
    auto_plan_scribe_enabled,
)


def test_auto_plan_scribe_enabled_default(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_AUTO_PLAN_SCRIBE", raising=False)
    assert auto_plan_scribe_enabled() is True
    monkeypatch.setenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "0")
    assert auto_plan_scribe_enabled() is False


def test_should_scribe_on_discuss_when_auto_enabled(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "1")
    assert _should_scribe_plan_after_turn(synthesize=False, cancelled=False) is True
    assert _should_scribe_plan_after_turn(synthesize=False, cancelled=True) is False


def test_should_not_scribe_discuss_when_auto_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "0")
    assert _should_scribe_plan_after_turn(synthesize=False, cancelled=False) is False
    assert _should_scribe_plan_after_turn(synthesize=True, cancelled=False) is True


def test_apply_scribe_runs_on_discuss_auto(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "1")
    with patch("agent_lab.room.synthesize_plan", return_value="## Plan\n\nupdated") as mock:
        out = _apply_scribe_after_turn(
            topic="t",
            messages=[{"role": "user", "content": "hi"}],
            run_meta={},
            plan_before="",
            mode="discuss",
            scribe=True,
            user_plan_send=False,
            cancelled=False,
            on_event=None,
        )
    mock.assert_called_once()
    assert "updated" in out
