"""Deterministic discuss harvest → Human Inbox question items (M3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from agent_lab.inbox_harvest import (
    clarifier_harvest_key,
    harvest_clarifier_questions,
    harvest_discuss_questions,
    harvest_question_candidates,
)
from agent_lab.session_clarifier import build_clarifier_questions


@dataclass
class _Msg:
    role: str
    agent: str | None = None
    content: str = ""
    envelope: dict[str, Any] | None = None


def _challenge(agent: str, message: str, refs: list[str] | None = None) -> _Msg:
    return _Msg(
        role="agent",
        agent=agent,
        content=message,
        envelope={"act": "CHALLENGE", "refs": refs or [], "message": message},
    )


_PLAN_OPEN = """\
## 합의

- 방향 확정

## 쟁점 / 미결정

- cadence 스윕 범위를 어디까지 둘지
"""


# --- pure candidate extraction -------------------------------------------------


def test_candidates_from_challenge():
    messages = [
        _Msg(role="user", content="topic"),
        _challenge("codex", "VU만 스윕하면 Theme 회귀를 놓친다", refs=["L42"]),
    ]
    cands = harvest_question_candidates(messages)
    assert len(cands) == 1
    c = cands[0]
    assert c.trigger == "T-Q1"
    assert c.refs == ("L42",)
    assert "codex CHALLENGE" in c.prompt
    assert "Theme" in c.excerpt


def test_candidates_ignore_endorse_and_pass():
    messages = [
        _Msg(role="user", content="topic"),
        _Msg(role="agent", agent="claude", content="ok", envelope={"act": "ENDORSE", "refs": []}),
        _Msg(role="agent", agent="cursor", content="nothing", envelope={"act": "PASS", "refs": []}),
    ]
    assert harvest_question_candidates(messages) == []


def test_candidates_from_plan_open():
    cands = harvest_question_candidates([], plan_md=_PLAN_OPEN)
    assert len(cands) == 1
    assert cands[0].trigger == "T-Q2"
    assert cands[0].refs == ("plan.md",)
    assert "cadence" in cands[0].excerpt


def test_candidates_cap_and_dedupe():
    msgs = [_Msg(role="user", content="t")]
    # same challenge text twice → one candidate; plus 4 distinct → capped at 3
    msgs.append(_challenge("codex", "dup challenge"))
    msgs.append(_challenge("claude", "dup challenge"))  # different agent → distinct key
    for i in range(4):
        msgs.append(_challenge("cursor", f"distinct {i}"))
    cands = harvest_question_candidates(msgs)
    assert len(cands) <= 3


# --- run_meta mutation ---------------------------------------------------------


def test_harvest_creates_question_no_options():
    run_meta: dict[str, Any] = {}
    messages = [
        _Msg(role="user", content="topic"),
        _challenge("codex", "스코프가 너무 넓다", refs=["L7"]),
    ]
    created = harvest_discuss_questions(run_meta, messages, human_turn=2)

    assert len(created) == 1
    item = created[0]
    assert item["kind"] == "question"
    assert item["source"] == "orchestrator"
    assert item["options"] == []  # M3: no options, no LLM synthesis
    assert item["status"] == "pending"
    assert item["trigger"] == "T-Q1"
    assert item["refs"] == ["L7"]
    assert item["human_turn_id"] == 2
    assert run_meta["human_inbox"][0]["id"] == item["id"]
    assert run_meta.get("inbox_pending") is True


def test_harvest_idempotent_across_turns():
    run_meta: dict[str, Any] = {}
    messages = [
        _Msg(role="user", content="topic"),
        _challenge("codex", "동일 쟁점"),
    ]
    first = harvest_discuss_questions(run_meta, messages)
    second = harvest_discuss_questions(run_meta, messages)
    assert len(first) == 1
    assert second == []  # same harvest_key already in inbox → not re-created
    assert len(run_meta["human_inbox"]) == 1


def test_harvest_skips_plan_mode():
    run_meta: dict[str, Any] = {}
    messages = [
        _Msg(role="user", content="topic"),
        _challenge("codex", "plan 모드에서는 objection으로"),
    ]
    created = harvest_discuss_questions(run_meta, messages, mode="plan")
    assert created == []
    assert "human_inbox" not in run_meta


def test_harvest_empty_turn_noop():
    run_meta: dict[str, Any] = {}
    messages = [
        _Msg(role="user", content="topic"),
        _Msg(role="agent", agent="claude", content="ok", envelope={"act": "ENDORSE", "refs": []}),
    ]
    assert harvest_discuss_questions(run_meta, messages) == []
    assert run_meta == {}


def test_clarifier_harvest_creates_t_q0_items(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "1")
    questions = build_clarifier_questions(
        "short topic",
        is_new_session=True,
        human_message_count=1,
    )
    assert questions is not None
    run_meta: dict[str, Any] = {}
    created = harvest_clarifier_questions(run_meta, questions, human_turn=1)
    assert len(created) == len(questions)
    assert all(item["trigger"] == "T-Q0" for item in created)
    assert all(item["options"] == [] for item in created)
    assert all(item["source"] == "orchestrator" for item in created)
    assert run_meta.get("inbox_pending") is True


def test_clarifier_harvest_idempotent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "1")
    questions = build_clarifier_questions(
        "short topic",
        is_new_session=True,
        human_message_count=1,
    )
    assert questions is not None
    run_meta: dict[str, Any] = {}
    first = harvest_clarifier_questions(run_meta, questions, human_turn=1)
    second = harvest_clarifier_questions(run_meta, questions, human_turn=1)
    assert len(first) == len(questions)
    assert second == []
    assert len(run_meta["human_inbox"]) == len(questions)


def test_clarifier_dedupe_matches_harvest_key():
    question = "이번 세션에서 가장 먼저 달성하려는 결과물은 무엇인가요? (파일·검증 기준 포함)"
    run_meta: dict[str, Any] = {}
    harvest_clarifier_questions(run_meta, [question], human_turn=1)
    key = clarifier_harvest_key(question)
    assert run_meta["human_inbox"][0]["harvest_key"] == key
    again = harvest_clarifier_questions(run_meta, [question], human_turn=1)
    assert again == []
