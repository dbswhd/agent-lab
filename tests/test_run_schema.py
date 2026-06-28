"""Tests for agent_lab.run.schema."""

from __future__ import annotations

import pytest

from agent_lab.run.schema import RuntimeValidationError, validate_run


def test_validate_run_rejects_invalid_mission_phase() -> None:
    with pytest.raises(RuntimeValidationError, match="invalid mission_loop.phase"):
        validate_run({"mission_loop": {"phase": "NOT_A_PHASE"}})


@pytest.mark.parametrize(
    "phase",
    [
        "MISSION_DEFINE",
        "DISCUSS",
        "PLAN_GATE",
        "PLAN_REJECT",
        "EXECUTE_QUEUE",
        "DRY_RUN",
        "MERGE_REVIEW",
        "VERIFY",
        "REPAIR",
        "MISSION_DONE",
        "MISSION_PAUSED",
    ],
)
def test_validate_run_accepts_valid_mission_phase(phase: str) -> None:
    validate_run({"mission_loop": {"phase": phase}})


def test_validate_run_rejects_invalid_execution_status() -> None:
    with pytest.raises(RuntimeValidationError, match="invalid execution status"):
        validate_run({"executions": [{"status": "bogus"}]})


@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "pending_approval",
        "review_required",
        "merge_conflict",
        "merged",
        "failed",
        "reverted",
        "cancelled",
    ],
)
def test_validate_run_accepts_valid_execution_status(status: str) -> None:
    validate_run({"executions": [{"status": status}]})


def test_validate_run_rejects_non_dict_execution_entry() -> None:
    with pytest.raises(RuntimeValidationError, match=r"execution\[0\] is not a dict"):
        validate_run({"executions": ["not-a-dict"]})


def test_validate_run_rejects_pending_action_indices_type() -> None:
    with pytest.raises(RuntimeValidationError, match="pending_action_indices must be a list of ints"):
        validate_run({"pending_action_indices": "1"})


def test_validate_run_accepts_empty_pending_action_indices() -> None:
    validate_run({"pending_action_indices": []})
