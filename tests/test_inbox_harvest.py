"""Deterministic discuss harvest → Human Inbox question items (M3)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from agent_lab.inbox.harvest import (
    clarifier_harvest_key,
    escalation_harvest_keys_from_batch,
    harvest_clarifier_questions,
    harvest_discuss_questions,
    harvest_question_candidates,
    record_escalation_harvest_keys,
)
from agent_lab.session.clarifier import build_clarifier_questions


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


def _fork_block(topic: str, options: list[tuple[str, list[str]]]) -> str:
    payload = {
        "topic": topic,
        "options": [{"label": label, "refs": refs} for label, refs in options],
    }
    return "토론:\n```decision-fork\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


_PLAN_OPEN = """\
## 합의

- 방향 확정

## 쟁점 / 미결정

- cadence 스윕 범위를 어디까지 둘지
"""


# --- pure candidate extraction -------------------------------------------------


def test_candidates_exclude_challenge_amend():
    messages = [
        _Msg(role="user", content="topic"),
        _challenge("codex", "VU만 스윕하면 Theme 회귀를 놓친다", refs=["L42"]),
    ]
    assert harvest_question_candidates(messages) == []


def test_candidates_from_decision_fork():
    messages = [
        _Msg(role="user", content="topic"),
        _Msg(role="agent", agent="codex", content=_fork_block("스윕 범위", [("VU만", ["L42"]), ("VU+Theme", ["L51"])])),
    ]
    cands = harvest_question_candidates(messages)
    assert len(cands) == 1
    c = cands[0]
    assert c.trigger == "T-Q1"
    assert len(c.options) == 2
    assert "L42" in c.refs


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


def test_candidates_cap_and_dedupe_plan_open():
    plan_md = "## 쟁점 / 미결정\n\n" + "\n".join(f"- open item {i}" for i in range(6))
    cands = harvest_question_candidates([], plan_md=plan_md)
    assert len(cands) == 3


# --- run_meta mutation ---------------------------------------------------------


def test_harvest_creates_fork_question_with_options():
    run_meta: dict[str, Any] = {}
    messages = [
        _Msg(role="user", content="topic"),
        _Msg(
            role="agent",
            agent="codex",
            content=_fork_block("스윕 범위", [("VU만", ["L7"]), ("전체", ["L8"])]),
        ),
    ]
    created = harvest_discuss_questions(run_meta, messages, human_turn=2)

    assert len(created) == 1
    item = created[0]
    assert item["kind"] == "question"
    assert item["source"] == "orchestrator"
    assert len(item["options"]) == 2
    assert item["status"] == "pending"
    assert item["trigger"] == "T-Q1"
    assert "L7" in item["refs"]
    assert item["human_turn_id"] == 2
    assert run_meta["human_inbox"][0]["id"] == item["id"]
    assert run_meta.get("inbox_pending") is True


def test_harvest_idempotent_across_turns():
    run_meta: dict[str, Any] = {}
    messages = [
        _Msg(role="user", content="topic"),
        _Msg(
            role="agent",
            agent="codex",
            content=_fork_block("동일 fork", [("A", ["L1"]), ("B", ["L2"])]),
        ),
    ]
    first = harvest_discuss_questions(run_meta, messages)
    second = harvest_discuss_questions(run_meta, messages)
    assert len(first) == 1
    assert second == []
    assert len(run_meta["human_inbox"]) == 1


def test_harvest_skips_plan_mode():
    run_meta: dict[str, Any] = {}
    messages = [
        _Msg(role="user", content="topic"),
        _Msg(
            role="agent",
            agent="codex",
            content=_fork_block("plan 모드", [("A", ["L1"]), ("B", ["L2"])]),
        ),
    ]
    created = harvest_discuss_questions(run_meta, messages, mode="plan")
    assert created == []
    assert "human_inbox" not in run_meta


def test_harvest_skips_escalation_consumed_challenge():
    messages = [
        _Msg(role="user", content="topic"),
        _challenge("codex", "rename만으론 호출부가 깨집니다"),
    ]
    keys = escalation_harvest_keys_from_batch(messages, act="CHALLENGE")
    assert len(keys) == 1
    run_meta: dict[str, Any] = {}
    record_escalation_harvest_keys(run_meta, messages, act="CHALLENGE")
    assert run_meta["_escalation_harvest_keys"] == keys
    created = harvest_discuss_questions(run_meta, messages, human_turn=1)
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
    assert all(isinstance(item.get("options"), list) for item in created)
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
