"""Named execution-status scopes for plan execute lifecycle.

Pick the scope that matches your gate — do not substitute one frozenset for
another without reading its docstring.

| Scope | Use when |
|-------|----------|
| ``PENDING_APPROVAL_ONLY`` | Dry-run awaiting Human approve only (runtime ``has_pending``, inbox T-B3) |
| ``OPEN_MERGE_PENDING_STATUSES`` | Open executions blocking merge / mission advance / handoff |
| ``EVIDENCE_PENDING_STATUSES`` | Evidence gates still "pending" (excludes ``merge_conflict``) |
| ``WORK_PHASE_MERGE_VERIFY_STATUSES`` | ``latest_execution`` rows that map to merge-verify UI step |
| ``CANCELLABLE_EXECUTION_STATUSES`` | User cancel / discard open dry-run or merge-review |
"""

from __future__ import annotations

from typing import Any

PENDING_APPROVAL_STATUS = "pending_approval"

# Historical alias — plan_execute facade and execute_shared imports.
PENDING_STATUS = PENDING_APPROVAL_STATUS

# Dry-run awaiting Human approve — NOT review_required / merge_conflict.
PENDING_APPROVAL_ONLY = frozenset({PENDING_APPROVAL_STATUS})

# Open executions that block merge, auto-merge, mission advance, external handoff.
OPEN_MERGE_PENDING_STATUSES = frozenset(
    {
        PENDING_APPROVAL_STATUS,
        "review_required",
        "merge_conflict",
        "pending",
    }
)

# Back-compat alias — merge_checks and auto_merge historically import this name.
OPEN_PENDING_STATUSES = OPEN_MERGE_PENDING_STATUSES

CANCELLABLE_EXECUTION_STATUSES = OPEN_MERGE_PENDING_STATUSES

# Evidence gates: pending manual/automated review (merge_conflict is a fail path).
EVIDENCE_PENDING_STATUSES = frozenset(
    {
        PENDING_APPROVAL_STATUS,
        "review_required",
        "pending",
    }
)

# Work stepper: latest_execution statuses that surface merge-verify phase.
WORK_PHASE_MERGE_VERIFY_STATUSES = frozenset(
    {
        "merged",
        "review_required",
        PENDING_APPROVAL_STATUS,
        "merge_conflict",
        "pending",
    }
)


def execution_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in (run.get("executions") or []) if isinstance(row, dict)]


def find_pending_approval_execution(run: dict[str, Any]) -> dict[str, Any] | None:
    """Latest execution with status ``pending_approval`` only."""
    for row in reversed(execution_rows(run)):
        if row.get("status") == PENDING_APPROVAL_STATUS:
            return row
    return None


def find_open_merge_pending_execution(
    run: dict[str, Any],
    *,
    execution_id: str | None = None,
) -> dict[str, Any] | None:
    """Latest open execution in ``OPEN_MERGE_PENDING_STATUSES``."""
    rows = execution_rows(run)
    if execution_id:
        for row in reversed(rows):
            if str(row.get("id") or "") != execution_id:
                continue
            if str(row.get("status") or "") in OPEN_MERGE_PENDING_STATUSES:
                return row
            return None
    for row in reversed(rows):
        if str(row.get("status") or "") in OPEN_MERGE_PENDING_STATUSES:
            return row
    return None
