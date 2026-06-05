"""LC-clarifier: session_clarifier discuss + plan mode gates."""

from __future__ import annotations

from typing import Any

import pytest

from agent_lab.inbox_harvest import harvest_clarifier_questions
from agent_lab.session_clarifier import build_clarifier_questions, clarifier_min_topic_chars


@pytest.fixture(autouse=True)
def _clarifier_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "1")


def test_clarifier_off_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    assert (
        build_clarifier_questions(
            "short",
            is_new_session=True,
            human_message_count=1,
        )
        is None
    )


def test_discuss_short_topic_returns_questions() -> None:
    qs = build_clarifier_questions(
        "short topic",
        is_new_session=True,
        human_message_count=1,
        plan_mode=False,
    )
    assert qs is not None
    assert len(qs) == 2
    assert "결과물" in qs[0]


def test_plan_mode_first_turn_returns_plan_questions() -> None:
    long_topic = "x" * (clarifier_min_topic_chars() + 10)
    qs = build_clarifier_questions(
        long_topic,
        is_new_session=True,
        human_message_count=1,
        plan_mode=True,
    )
    assert qs is not None
    assert len(qs) == 2
    assert any("plan.md" in q for q in qs)


def test_plan_mode_long_topic_first_turn_still_questions() -> None:
    long_topic = "Implement durable session resume with regression coverage and docs."
    assert len(long_topic) >= clarifier_min_topic_chars()
    qs = build_clarifier_questions(
        long_topic,
        is_new_session=True,
        human_message_count=1,
        plan_mode=True,
    )
    assert qs is not None
    assert len(qs) == 2
    assert "검증" in qs[0]


def test_plan_mode_second_turn_returns_none_unless_short() -> None:
    long_topic = "x" * (clarifier_min_topic_chars() + 10)
    assert (
        build_clarifier_questions(
            long_topic,
            is_new_session=False,
            human_message_count=2,
            plan_mode=True,
        )
        is None
    )
    short_qs = build_clarifier_questions(
        "short",
        is_new_session=False,
        human_message_count=2,
        plan_mode=True,
    )
    assert short_qs is not None
    assert any("plan.md" in q for q in short_qs)


def test_clarifier_questions_surface_to_inbox() -> None:
    qs = build_clarifier_questions(
        "short topic",
        is_new_session=True,
        human_message_count=1,
    )
    assert qs is not None
    run_meta: dict[str, Any] = {}
    created = harvest_clarifier_questions(run_meta, qs, human_turn=1)
    assert len(created) == len(qs)
    assert run_meta["human_inbox"][0]["kind"] == "question"
    assert run_meta["human_inbox"][0]["trigger"] == "T-Q0"
