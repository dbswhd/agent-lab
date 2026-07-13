from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.mission.decision_queue import (
    AnswerDecision,
    DecisionStatus,
    DecisionTransitionError,
    ExpireDecision,
    apply_decision_event,
    decide_decision,
    new_decision,
)
from agent_lab.mission.decision_repository import DecisionRepository


def test_human_decision_answer_resumes_wait_without_worker_state() -> None:
    decision = new_decision("d-1", "m-1", "Approve merge?", "merge")
    answered = decide_decision(decision, AnswerDecision("yes"))
    decision = apply_decision_event(decision, answered[0])

    assert decision.status is DecisionStatus.ANSWERED
    assert decision.answer == "yes"


def test_stale_human_answer_is_rejected() -> None:
    decision = new_decision("d-2", "m-1", "Choose provider", "provider")

    with pytest.raises(DecisionTransitionError, match="expected version 1"):
        decide_decision(decision, AnswerDecision("claude"), expected_version=1)


def test_answer_is_not_accepted_after_expiry() -> None:
    decision = new_decision("d-3", "m-1", "Continue?", "continue")
    expired = decide_decision(decision, ExpireDecision())
    decision = apply_decision_event(decision, expired[0])

    with pytest.raises(DecisionTransitionError, match="terminal"):
        decide_decision(decision, AnswerDecision("no"))


def test_decision_repository_restarts_with_pending_answer(tmp_path: Path) -> None:
    decision = new_decision("d-4", "m-1", "Approve merge?", "merge")
    path = tmp_path / "decision.jsonl"
    repository = DecisionRepository(path, decision)

    answered = repository.answer(AnswerDecision("yes"))
    restored = DecisionRepository(path, decision).load()

    assert answered == restored
    assert restored.status is DecisionStatus.ANSWERED


def test_decision_repository_rejects_replay_into_another_identity(tmp_path: Path) -> None:
    path = tmp_path / "decision.jsonl"
    first = new_decision("d-5", "m-1", "Approve?", "merge")
    DecisionRepository(path, first).answer(AnswerDecision("yes"))
    second = new_decision("d-6", "m-2", "Different?", "merge")

    with pytest.raises(ValueError, match="identity"):
        DecisionRepository(path, second).load()
