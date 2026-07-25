"""P1 stage 2: a plan with no executable action gets one corrective scribe retry.

Stage 1 made dead plans *detectable*; this makes them *rare*. The retry feeds the
specific diagnostic back to the scribe and is kept only if it actually produces an
executable plan — a repair must never degrade the plan it was trying to fix.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from agent_lab.plan.artifact import build_plan_artifact, scribe_repair_instruction
from agent_lab.room.plan_scribe import _repair_dead_plan, plan_scribe_repair_attempts

GOOD_PLAN = """# Title

## 지금 실행

1. Fix the typo
   - 무엇을: correct `roompy` to `room.py`
   - 어디서: `docs/x2-lift.md`
   - 검증: `grep -c 'room.py' docs/x2-lift.md`
"""

DEAD_PLAN = """# X2 lift dogfood

## TL;DR

> Summary: fix one typo.

## Notes

Prose that never declares an executable section.
"""

STUB_PLAN = "# X2"


class FakeRoom:
    """Stands in for the agent_lab.room module's synthesize_plan."""

    def __init__(self, *replies: str, raises: bool = False) -> None:
        self._replies = list(replies)
        self._raises = raises
        self.calls: list[dict[str, Any]] = []

    def synthesize_plan(self, topic, messages, *, run_meta=None, repair_hint=None):  # noqa: ANN001
        self.calls.append({"topic": topic, "repair_hint": repair_hint})
        if self._raises:
            raise RuntimeError("scribe exploded")
        return self._replies.pop(0) if self._replies else ""


def _events() -> tuple[list[tuple[str, dict]], Any]:
    seen: list[tuple[str, dict]] = []
    return seen, lambda name, payload: seen.append((name, payload))


def _repair(room: FakeRoom, plan: str, on_event=None) -> str:  # noqa: ANN001
    return _repair_dead_plan(
        room,
        plan,
        topic="t",
        messages=[SimpleNamespace(role="user", content="hi")],  # type: ignore[list-item]
        run_meta={},
        on_event=on_event,
    )


@pytest.fixture(autouse=True)
def _enable_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt in explicitly — repair is skipped under mock agents by default."""
    monkeypatch.setenv("AGENT_LAB_PLAN_SCRIBE_REPAIR", "1")


# --- gating -----------------------------------------------------------------


def test_repair_skipped_under_mock_agents_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retrying a fixed mock stub burns a call and proves nothing."""
    monkeypatch.delenv("AGENT_LAB_PLAN_SCRIBE_REPAIR", raising=False)
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    assert plan_scribe_repair_attempts() == 0


def test_explicit_flag_overrides_mock_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_PLAN_SCRIBE_REPAIR", "1")
    assert plan_scribe_repair_attempts() == 1


def test_flag_can_disable_and_set_attempt_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAN_SCRIBE_REPAIR", "0")
    assert plan_scribe_repair_attempts() == 0
    monkeypatch.setenv("AGENT_LAB_PLAN_SCRIBE_REPAIR", "3")
    assert plan_scribe_repair_attempts() == 3


def test_disabled_repair_is_a_no_op() -> None:
    room = FakeRoom(GOOD_PLAN)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AGENT_LAB_PLAN_SCRIBE_REPAIR", "0")
        assert _repair(room, DEAD_PLAN) == DEAD_PLAN
    assert room.calls == []


# --- the happy path ---------------------------------------------------------


def test_healthy_plan_is_never_retried() -> None:
    room = FakeRoom(GOOD_PLAN)
    assert _repair(room, GOOD_PLAN) == GOOD_PLAN
    assert room.calls == [], "an executable plan must not cost an extra scribe call"


def test_dead_plan_is_repaired() -> None:
    room = FakeRoom(GOOD_PLAN)
    assert _repair(room, DEAD_PLAN) == GOOD_PLAN
    assert len(room.calls) == 1


def test_retry_carries_the_specific_diagnostic() -> None:
    room = FakeRoom(GOOD_PLAN)
    _repair(room, DEAD_PLAN)
    hint = room.calls[0]["repair_hint"]
    assert "no executable section header" in hint
    assert "지금 실행" in hint
    assert "무엇을" in hint and "어디서" in hint and "검증" in hint


def test_stub_and_missing_header_get_different_hints() -> None:
    stub_room, dead_room = FakeRoom(GOOD_PLAN), FakeRoom(GOOD_PLAN)
    _repair(stub_room, STUB_PLAN)
    _repair(dead_room, DEAD_PLAN)
    assert "empty or a stub" in stub_room.calls[0]["repair_hint"]
    assert "no executable section header" in dead_room.calls[0]["repair_hint"]


# --- never degrade ----------------------------------------------------------


def test_failed_repair_keeps_the_original_plan() -> None:
    """A retry that is also dead must not replace the original."""
    room = FakeRoom(STUB_PLAN)
    assert _repair(room, DEAD_PLAN) == DEAD_PLAN


def test_scribe_exception_during_repair_keeps_original() -> None:
    room = FakeRoom(raises=True)
    assert _repair(room, DEAD_PLAN) == DEAD_PLAN


def test_empty_retry_keeps_the_original_plan() -> None:
    room = FakeRoom("")
    assert _repair(room, DEAD_PLAN) == DEAD_PLAN


def test_multiple_attempts_stop_at_first_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAN_SCRIBE_REPAIR", "3")
    room = FakeRoom(STUB_PLAN, GOOD_PLAN, GOOD_PLAN)
    assert _repair(room, DEAD_PLAN) == GOOD_PLAN
    assert len(room.calls) == 2


def test_attempts_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAN_SCRIBE_REPAIR", "2")
    room = FakeRoom(STUB_PLAN, STUB_PLAN, GOOD_PLAN)
    assert _repair(room, DEAD_PLAN) == DEAD_PLAN
    assert len(room.calls) == 2, "must not retry past the configured attempt cap"


# --- observability ----------------------------------------------------------


def test_repair_is_observable() -> None:
    seen, on_event = _events()
    _repair(FakeRoom(GOOD_PLAN), DEAD_PLAN, on_event)
    names = [n for n, _ in seen]
    assert "plan_scribe_repair" in names
    assert "plan_scribe_repair_ok" in names
    start = next(p for n, p in seen if n == "plan_scribe_repair")
    assert start["reason"] == "no_section_header"
    assert start["attempt"] == 1


def test_exhausted_repair_is_observable() -> None:
    seen, on_event = _events()
    _repair(FakeRoom(STUB_PLAN), DEAD_PLAN, on_event)
    assert "plan_scribe_repair_exhausted" in [n for n, _ in seen]


def test_failed_repair_is_observable() -> None:
    seen, on_event = _events()
    _repair(FakeRoom(raises=True), DEAD_PLAN, on_event)
    assert "plan_scribe_repair_failed" in [n for n, _ in seen]


# --- instruction builder ----------------------------------------------------


def test_no_instruction_for_healthy_plan() -> None:
    assert scribe_repair_instruction(build_plan_artifact(GOOD_PLAN)) == ""


def test_instruction_is_actionable() -> None:
    text = scribe_repair_instruction(build_plan_artifact(DEAD_PLAN))
    assert "Rewrite the plan" in text
    assert "Keep the rest of the plan's content" in text
