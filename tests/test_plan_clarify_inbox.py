"""Plan CLARIFY multiple-choice inbox seeding."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.plan.clarify_options import options_for_clarifier_category
from agent_lab.plan.workflow import (
    ensure_plan_clarify_inbox_question,
    ensure_plan_clarify_interview,
    init_plan_workflow_on_plan_send,
)
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.session.clarifier import persist_clarifier_interview


def test_clarifier_category_options_have_at_least_two_choices() -> None:
    for cat in ("goal", "constraints", "criteria", "context", "scope", "verify"):
        opts = options_for_clarifier_category(cat)
        assert len(opts) >= 2
        assert all(o.get("id") and o.get("label") for o in opts)


def test_ensure_plan_clarify_interview_skips_smoke_test_topic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    init_plan_workflow_on_plan_send(folder)
    patch_run_meta(folder, lambda r: {**r, "topic": "코덱스 응답 테스트 중"})
    assert ensure_plan_clarify_interview(folder) is None
    assert ensure_plan_clarify_inbox_question(folder) is None


def test_ensure_plan_clarify_inbox_question_seeds_multiple_choice(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    init_plan_workflow_on_plan_send(folder)
    interview = {
        "version": 2,
        "plan_mode": True,
        "status": "pending",
        "source": "test",
        "human_turn": 1,
        "questions": [
            {
                "id": "goal",
                "category": "goal",
                "prompt": "이번 작업의 목표는?",
                "options": options_for_clarifier_category("goal"),
            }
        ],
        "answers": {},
    }
    persist_clarifier_interview(folder, interview)
    item = ensure_plan_clarify_inbox_question(folder)
    assert item is not None
    assert item.get("kind") == "question"
    assert len(item.get("options") or []) >= 2
    run = read_run_meta(folder)
    from agent_lab.human_inbox import has_pending_question

    assert has_pending_question(run)


def test_ensure_plan_clarify_inbox_question_idempotent(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    init_plan_workflow_on_plan_send(folder)
    interview = {
        "version": 2,
        "plan_mode": True,
        "status": "pending",
        "source": "test",
        "human_turn": 1,
        "questions": [
            {
                "id": "criteria",
                "category": "criteria",
                "prompt": "완료 검증은?",
                "options": options_for_clarifier_category("criteria"),
            }
        ],
        "answers": {},
    }
    persist_clarifier_interview(folder, interview)
    first = ensure_plan_clarify_inbox_question(folder)
    second = ensure_plan_clarify_inbox_question(folder)
    assert first is not None
    assert second is not None
    assert first.get("id") == second.get("id")
