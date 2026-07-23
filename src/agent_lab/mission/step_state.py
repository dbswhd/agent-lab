from __future__ import annotations

"""Pure, read-only derivation of a per-action "step phase" from an execution row.

This is a characterization tool, not a behavior change: `mission_loop.phase`
(EXECUTE_QUEUE/DRY_RUN/MERGE_REVIEW/VERIFY/REPAIR) is largely redundant with the
current action's own execution-row `status`/`oracle`/`repair_history` (see
`core/execution_status_scopes.py` for the named status scopes this reuses). Nothing
in the mission FSM reads or writes through this module yet — `scripts/step_state_parity_audit.py`
uses it to measure how often the two signals actually agree before any orchestration
code is switched to depend on it.
"""

from typing import Any, Literal

from agent_lab.core.execution_status_scopes import OPEN_MERGE_PENDING_STATUSES

StepPhase = Literal[
    "NOT_STARTED",
    "DRY_RUN",
    "MERGE_REVIEW",
    "VERIFYING",
    "REPAIRING",
    "VERIFIED",
    "FAILED",
]

# Rows created but not yet merged (worktree/dry-run in flight, or awaiting Human
# merge decision) — DRY_RUN and MERGE_REVIEW are collapsed to MERGE_REVIEW here
# since "pending" alone doesn't distinguish an in-progress dry-run call from one
# already awaiting Human review; the audit records disagreement rather than guess.
_MERGE_REVIEW_STATUSES = OPEN_MERGE_PENDING_STATUSES

_FAILED_STATUSES = frozenset({"rejected", "cancelled"})
_VERIFIED_STATUSES = frozenset({"completed"})


def derive_step_phase(row: dict[str, Any] | None) -> StepPhase | None:
    """Derive a step phase from a single execution row. Returns None when the
    row's status doesn't map to a known bucket (e.g. ``blocked_isolation``) --
    an unmapped status is reported as such, never guessed."""
    if not isinstance(row, dict):
        return "NOT_STARTED"
    status = str(row.get("status") or "")
    if not status:
        return "NOT_STARTED"
    if status in _MERGE_REVIEW_STATUSES:
        return "MERGE_REVIEW"
    if status in _FAILED_STATUSES:
        return "FAILED"
    if status in _VERIFIED_STATUSES:
        return "VERIFIED"
    if status == "merged":
        oracle = row.get("oracle")
        oracle = oracle if isinstance(oracle, dict) else {}
        verdict = str(oracle.get("verdict") or "").lower()
        if verdict == "pass":
            return "VERIFIED"
        if verdict == "fail":
            repair_history = row.get("repair_history")
            if isinstance(repair_history, list) and repair_history:
                return "REPAIRING"
            return "FAILED"
        return "VERIFYING"
    return None


def repair_count_from_history(row: dict[str, Any] | None) -> int:
    """Alternative repair-count signal: length of the row's own repair_history,
    to compare against ``mission_loop.action_repair_counts[idx]``."""
    if not isinstance(row, dict):
        return 0
    history = row.get("repair_history")
    return len(history) if isinstance(history, list) else 0
