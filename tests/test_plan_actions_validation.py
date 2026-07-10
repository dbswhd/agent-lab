"""Plan-actions validation after scribe."""

from __future__ import annotations

from agent_lab.plan.actions import validate_plan_actions_format
from agent_lab.room.plan_scribe import _emit_plan_actions_validation

NEW_FORMAT_PLAN = """## 지금 실행
1.
   - 무엇을: example task.
   - 어디서: `plan_actions.py`
   - 검증: pytest passes.
   (ref: chat.jsonl#L1)

## 실행 순서 (이후)
2. defer UI. (ref: chat.jsonl#L2)
"""

RICH_FORMAT_PLAN = """## TL;DR
> Summary: example
> Deliverables: patch
> Risk: Low — demo

## Must
- ship validation

## Must-NOT
- rewrite unrelated modules

## Parallel waves
Wave 1: validation helper

## Evidence paths
- `tests/test_plan_actions_validation.py`

## 지금 실행
1.
   - 무엇을: example task.
   - 어디서: `plan_actions.py`
   - 검증: pytest passes.
   (ref: chat.jsonl#L1)

## 실행 순서 (이후)
2. defer UI. (ref: chat.jsonl#L2)
"""

BAD_PLAN_NO_EXECUTE = """## 합의된 점
- nothing actionable yet.
"""


def test_validate_plan_actions_ok():
    result = validate_plan_actions_format(NEW_FORMAT_PLAN)
    assert result["ok"] is True
    assert result["has_now_section"] is True
    assert result["recommended_action_key"] == "now:1"
    assert "missing_tldr" in result["soft_issues"]
    assert "missing_must_not" in result["soft_issues"]


def test_validate_plan_actions_rich_contract_no_soft_issues():
    result = validate_plan_actions_format(RICH_FORMAT_PLAN)
    assert result["ok"] is True
    assert result["soft_issues"] == []


def test_validate_plan_actions_missing_section():
    result = validate_plan_actions_format(BAD_PLAN_NO_EXECUTE)
    assert result["ok"] is False
    assert "missing_execute_section" in result["issues"]
    assert result["soft_issues"] == []


def test_emit_plan_actions_validation_after_scribe_mock():
    events: list[tuple[str, dict]] = []

    def on_event(name: str, payload: dict) -> None:
        events.append((name, payload))

    _emit_plan_actions_validation(BAD_PLAN_NO_EXECUTE, on_event)

    assert any(name == "plan_actions_validation" for name, _ in events)
    _, payload = next(item for item in events if item[0] == "plan_actions_validation")
    assert payload["ok"] is False
    assert "missing_execute_section" in payload["issues"]
