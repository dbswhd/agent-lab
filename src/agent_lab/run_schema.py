"""Runtime schema validation for run.json state."""

from __future__ import annotations

from typing import Any


class RuntimeValidationError(Exception):
    """Raised when run.json state violates runtime invariants."""


_VALID_MISSION_PHASES = frozenset(
    {
        "MISSION_DEFINE",
        "CLARIFY",
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
    }
)

_VALID_EXECUTION_STATUSES = frozenset(
    {
        "pending",
        "pending_approval",
        "review_required",
        "merge_conflict",
        "merged",
        "failed",
        "reverted",
        "cancelled",
        # Canonical execution statuses also emitted by plan_execute but previously
        # absent from this set (shipped regression baselines carry them); crash
        # recovery's patch_run_meta validates the whole run, so these must be valid.
        "completed",
        "rejected",
        "blocked_isolation",
        "superseded",
    }
)


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value)


def validate_run(run: dict[str, Any]) -> None:
    mission_loop = run.get("mission_loop") if isinstance(run.get("mission_loop"), dict) else None
    if mission_loop is not None:
        phase = _as_str(mission_loop.get("phase"))
        if phase is not None and phase not in _VALID_MISSION_PHASES:
            raise RuntimeValidationError(f"invalid mission_loop.phase: {phase!r}")

    executions = run.get("executions") if isinstance(run.get("executions"), list) else None
    if executions is not None:
        for index, execution in enumerate(executions):
            if not isinstance(execution, dict):
                raise RuntimeValidationError(f"execution[{index}] is not a dict")
            status = _as_str(execution.get("status"))
            if status is not None and status not in _VALID_EXECUTION_STATUSES:
                raise RuntimeValidationError(f"invalid execution status at {index}: {status!r}")

    pending = run.get("pending_action_indices")
    if pending is not None:
        if not isinstance(pending, list) or not all(isinstance(item, int) for item in pending):
            raise RuntimeValidationError("pending_action_indices must be a list of ints")

    goal_ledger = run.get("goal_ledger")
    if goal_ledger is not None:
        if not isinstance(goal_ledger, list) or not all(isinstance(entry, dict) for entry in goal_ledger):
            raise RuntimeValidationError("goal_ledger must be a list of dicts")
