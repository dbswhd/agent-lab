"""Execution status scope matrix — documents intentional semantic splits."""

from __future__ import annotations

from agent_lab.plan.execution_status_scopes import (
    CANCELLABLE_EXECUTION_STATUSES,
    EVIDENCE_PENDING_STATUSES,
    OPEN_MERGE_PENDING_STATUSES,
    PENDING_APPROVAL_ONLY,
    PENDING_APPROVAL_STATUS,
    WORK_PHASE_MERGE_VERIFY_STATUSES,
    find_open_merge_pending_execution,
    find_pending_approval_execution,
)


def test_pending_approval_only_is_strict_subset_of_open_merge():
    assert PENDING_APPROVAL_ONLY < OPEN_MERGE_PENDING_STATUSES


def test_evidence_pending_excludes_merge_conflict():
    assert "merge_conflict" not in EVIDENCE_PENDING_STATUSES
    assert PENDING_APPROVAL_STATUS in EVIDENCE_PENDING_STATUSES


def test_work_phase_includes_merged_but_not_completed():
    assert "merged" in WORK_PHASE_MERGE_VERIFY_STATUSES
    assert "completed" not in WORK_PHASE_MERGE_VERIFY_STATUSES


def test_find_pending_approval_ignores_review_required():
    run = {
        "executions": [
            {"id": "a", "status": "review_required"},
            {"id": "b", "status": PENDING_APPROVAL_STATUS},
        ]
    }
    assert find_pending_approval_execution(run) == {"id": "b", "status": PENDING_APPROVAL_STATUS}


def test_find_open_merge_pending_matches_broader_set():
    run = {
        "executions": [
            {"id": "a", "status": "review_required"},
            {"id": "b", "status": PENDING_APPROVAL_STATUS},
        ]
    }
    assert find_open_merge_pending_execution(run) == {
        "id": "b",
        "status": PENDING_APPROVAL_STATUS,
    }
    assert find_open_merge_pending_execution(run, execution_id="a") == {
        "id": "a",
        "status": "review_required",
    }


def test_cancellable_matches_open_merge_pending():
    assert CANCELLABLE_EXECUTION_STATUSES == OPEN_MERGE_PENDING_STATUSES
