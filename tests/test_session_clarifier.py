"""LC-clarifier + MB-7 interview v2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_lab.inbox.harvest import harvest_clarifier_questions
from agent_lab.plan.workflow import get_plan_workflow
from agent_lab.run.meta import read_run_meta
from agent_lab.session.clarifier import (
    build_clarifier_interview,
    build_clarifier_questions,
    clarifier_min_topic_chars,
    interview_prompts,
    persist_clarifier_interview,
    public_clarifier_interview,
    record_clarifier_answers,
)

try:
    from fastapi.testclient import TestClient

    from app.server.main import app

    _HAS_TEST_CLIENT = True
except ImportError:
    _HAS_TEST_CLIENT = False


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
    assert len(qs) >= 2


def test_plan_mode_first_turn_interview_v2() -> None:
    long_topic = "x" * (clarifier_min_topic_chars() + 10)
    interview = build_clarifier_interview(
        long_topic,
        is_new_session=True,
        human_message_count=1,
        plan_mode=True,
    )
    assert interview is not None
    assert interview["version"] == 2
    prompts = interview_prompts(interview)
    assert prompts is not None
    assert len(prompts) >= 3


def test_plan_mode_long_topic_first_turn_still_questions() -> None:
    long_topic = "Implement durable session resume with regression coverage and docs."
    assert len(long_topic) >= clarifier_min_topic_chars()
    interview = build_clarifier_interview(
        long_topic,
        is_new_session=True,
        human_message_count=1,
        plan_mode=True,
    )
    assert interview is not None
    categories = [q.get("category") for q in interview.get("questions") or []]
    assert "criteria" in categories


def test_plan_mode_second_turn_still_returns_questions_for_unclear() -> None:
    # Engine is always-on: vague topics generate questions regardless of turn count.
    long_topic = "x" * (clarifier_min_topic_chars() + 10)
    qs = build_clarifier_questions(
        long_topic,
        is_new_session=False,
        human_message_count=2,
        plan_mode=True,
    )
    assert qs is not None
    assert len(qs) >= 1


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


def test_persist_and_record_clarifier_answers(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    interview = build_clarifier_interview(
        "short topic",
        is_new_session=True,
        human_message_count=1,
        plan_mode=True,
    )
    assert interview is not None
    persist_clarifier_interview(folder, interview)
    qids = [str(q["id"]) for q in interview["questions"]]
    record_clarifier_answers(
        folder,
        answers={qids[0]: "answer one", qids[1]: "answer two"},
        mark_complete=False,
    )
    public = public_clarifier_interview(read_run_meta(folder))
    assert public is not None
    assert public["answers"][qids[0]] == "answer one"


@pytest.mark.skipif(not _HAS_TEST_CLIENT, reason="FastAPI test client unavailable")
def test_clarifier_answers_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent_lab.session.SESSIONS_DIR", tmp_path)
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", tmp_path)
    folder = tmp_path / "api-sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    interview = build_clarifier_interview(
        "short topic",
        is_new_session=True,
        human_message_count=1,
        plan_mode=True,
    )
    assert interview is not None
    persist_clarifier_interview(folder, interview)
    qid = str(interview["questions"][0]["id"])
    client = TestClient(app)
    res = client.post(
        f"/api/sessions/{folder.name}/clarifier-interview/answers",
        json={"answers": {qid: "scope is src/ only"}, "mark_complete": False},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["interview"]["answers"][qid] == "scope is src/ only"


@pytest.mark.skipif(not _HAS_TEST_CLIENT, reason="FastAPI test client unavailable")
def test_clarifier_answers_api_complete_auto_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Submitting all answers with mark_complete=True must auto-advance CLARIFY→DRAFT."""
    monkeypatch.setattr("agent_lab.session.SESSIONS_DIR", tmp_path)
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", tmp_path)
    folder = tmp_path / "api-sess2"
    folder.mkdir()
    # Anchored goal so clarity gate short-circuits immediately after answers are submitted.
    (folder / "run.json").write_text(
        '{"verified_loop": {"loop_goal": {"text": "fix src/agent_lab/run_meta.py null check"}}}',
        encoding="utf-8",
    )
    from agent_lab.plan.workflow import init_plan_workflow_on_plan_send

    init_plan_workflow_on_plan_send(folder)
    assert get_plan_workflow(read_run_meta(folder))["phase"] == "CLARIFY"

    interview = build_clarifier_interview(
        "short topic",
        is_new_session=True,
        human_message_count=1,
        plan_mode=True,
    )
    assert interview is not None
    persist_clarifier_interview(folder, interview)

    qids = [str(q["id"]) for q in interview["questions"]]
    answers = {qid: "answer" for qid in qids}

    client = TestClient(app)
    res = client.post(
        f"/api/sessions/{folder.name}/clarifier-interview/answers",
        json={"answers": answers, "mark_complete": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["interview"]["status"] == "complete"
    # Auto-advance: CLARIFY→DRAFT without a separate chat turn
    assert body.get("plan_workflow", {}).get("phase") == "DRAFT"


def test_legacy_interview_when_v2_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    # When AGENT_LAB_CLARIFIER_INTERVIEW=off and engine returns None (e.g. anchored topic),
    # the legacy 2-question path activates for short/first-turn topics.
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_INTERVIEW", "off")
    monkeypatch.setattr(
        "agent_lab.clarifier_engine.build_engine_interview",
        lambda *a, **kw: None,
    )
    long_topic = "x" * (clarifier_min_topic_chars() + 10)
    qs = build_clarifier_questions(
        long_topic,
        is_new_session=True,
        human_message_count=1,
        plan_mode=True,
    )
    assert qs is not None
    assert len(qs) == 2
    assert "검증" in qs[0]
