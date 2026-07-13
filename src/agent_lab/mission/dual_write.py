from __future__ import annotations

import functools
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from agent_lab.env_flags import is_truthy
from agent_lab.mission.application import MissionApplication, MissionApplicationError
from agent_lab.mission.dual_write_observability import record_dual_write_event
from agent_lab.mission.kernel import (
    ApproveDiff,
    CloseExecutionGate,
    MarkDiffReady,
    MissionState,
    OpenExecutionGate,
    OracleVerdict,
    RecordMerge,
    RecordOracle,
    ResolveBlock,
    StartExecution,
)
from agent_lab.mission.errors import MissionTransitionError
from agent_lab.mission.repository import MissionRepository
from agent_lab.run.meta import read_run_meta


def _observed(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Log + count every mirror_* outcome, regardless of which return path it took.

    Every mirror_* function's first positional arg is the session ``folder`` and
    every return value is a dict carrying ``enabled``/``mirrored``/``operation``/
    ``reason`` — wrapping the call site (rather than instrumenting each of the
    ~10 internal return statements individually) guarantees no exit path is missed.
    """

    @functools.wraps(fn)
    def wrapper(folder: Path, *args: Any, **kwargs: Any) -> dict[str, Any]:
        result = fn(folder, *args, **kwargs)
        return record_dual_write_event(folder, result)

    return wrapper


def _cohort_ids() -> frozenset[str]:
    raw = (os.getenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS") or "").strip()
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def dual_write_enabled(folder: Path | None = None) -> bool:
    if not is_truthy(os.getenv("AGENT_LAB_MISSION_DUAL_WRITE")):
        return False
    cohort = _cohort_ids()
    return not cohort or (folder is not None and folder.name in cohort)


def _blocked_result(folder: Path, operation: str) -> dict[str, Any] | None:
    if not is_truthy(os.getenv("AGENT_LAB_MISSION_DUAL_WRITE")):
        return {"enabled": False, "operation": operation, "mirrored": False}
    if not dual_write_enabled(folder):
        return _result(operation=operation, mirrored=False, reason="cohort_not_selected")
    return None


def _goal(folder: Path, explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    run = read_run_meta(folder)
    for key in ("goal", "topic"):
        value = run.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    session_goal = run.get("session_goal")
    if isinstance(session_goal, dict) and str(session_goal.get("text") or "").strip():
        return str(session_goal["text"]).strip()
    return folder.name


def _result(*, operation: str, mirrored: bool, reason: str = "") -> dict[str, Any]:
    return {"enabled": True, "operation": operation, "mirrored": mirrored, "reason": reason}


@_observed
def mirror_plan_approval(folder: Path, *, goal: str | None = None) -> dict[str, Any]:
    blocked = _blocked_result(folder, "plan_approve")
    if blocked is not None:
        return blocked
    try:
        mission = MissionApplication(folder, _goal(folder, goal)).approve_plan()
    except (MissionApplicationError, MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="plan_approve", mirrored=False, reason=str(exc)[:240])
    return {**_result(operation="plan_approve", mirrored=True), "state": mission.state.value, "version": mission.version}


@_observed
def mirror_plan_rejection(folder: Path, *, note: str = "", goal: str | None = None) -> dict[str, Any]:
    blocked = _blocked_result(folder, "plan_reject")
    if blocked is not None:
        return blocked
    try:
        mission = MissionApplication(folder, _goal(folder, goal)).reject_plan(note)
    except (MissionApplicationError, MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="plan_reject", mirrored=False, reason=str(exc)[:240])
    return {**_result(operation="plan_reject", mirrored=True), "state": mission.state.value, "version": mission.version}


@_observed
def mirror_inbox_creation(folder: Path, *, item_id: str, kind: str = "", reason: str = "") -> dict[str, Any]:
    """Open an execution-level gate when a human question/build item is created.

    Uses ``OpenExecutionGate`` — valid from any ``MissionState``, purely
    observational, never blocks other transitions (kernel.py; see
    docs/redesign-2026-07/execution-gate-design-draft-2026-07-13.md) — instead
    of ``BlockExecution`` (valid only from READY_TO_EXECUTE, blocks
    StartExecution). Most real inbox items fire mid-execution (merge_gate.py,
    autonomy_inbox.py, room/retry.py, ...) where BlockExecution used to
    silently no-op; this mirrors regardless of what Mission is doing.
    """
    blocked = _blocked_result(folder, "inbox_create")
    if blocked is not None:
        return blocked
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal.is_file():
        return _result(operation="inbox_create", mirrored=False, reason="mission_journal_missing")
    repo = MissionRepository(journal, folder.name, _goal(folder))
    try:
        mission = repo.dispatch(OpenExecutionGate(item_id, kind, reason), idempotency_key=f"gate-open:{item_id}")
    except (MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="inbox_create", mirrored=False, reason=str(exc)[:240])
    return {
        **_result(operation="inbox_create", mirrored=True),
        "state": mission.state.value,
        "open_gate_count": len(mission.open_gates),
    }


@_observed
def mirror_inbox_resolution(folder: Path, *, item_id: str, answer: str = "") -> dict[str, Any]:
    """Close the execution-level gate for this item, if one is open.

    Also resolves the (independent, unrelated) pre-execution
    ``BlockExecution``/``AWAITING_HUMAN`` gate when Mission happens to be
    sitting in it — that mechanism is untouched and still valid, just no
    longer the only thing this bridge understands.
    """
    blocked = _blocked_result(folder, "inbox_resolve")
    if blocked is not None:
        return blocked
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal.is_file():
        return _result(operation="inbox_resolve", mirrored=False, reason="mission_journal_missing")
    repo = MissionRepository(journal, folder.name, _goal(folder))
    mission = repo.load()
    try:
        if mission.state is MissionState.AWAITING_HUMAN:
            mission = repo.dispatch(ResolveBlock(), idempotency_key=f"inbox-resolve:{item_id}:{answer.strip()}")
        mission = repo.dispatch(CloseExecutionGate(item_id), idempotency_key=f"gate-close:{item_id}")
    except (MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="inbox_resolve", mirrored=False, reason=str(exc)[:240])
    return {
        **_result(operation="inbox_resolve", mirrored=True),
        "state": mission.state.value,
        "open_gate_count": len(mission.open_gates),
    }


@_observed
def mirror_execution_transition(
    folder: Path,
    *,
    execution: dict[str, Any],
    phase: Literal["approve", "reject", "merge", "oracle"],
) -> dict[str, Any]:
    blocked = _blocked_result(folder, f"execution_{phase}")
    if blocked is not None:
        return blocked
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal.is_file():
        return _result(operation=f"execution_{phase}", mirrored=False, reason="mission_journal_missing")
    repo = MissionRepository(journal, folder.name, _goal(folder))
    mission = repo.load()
    execution_id = str(execution.get("id") or execution.get("execution_id") or "unknown")
    try:
        if phase == "reject":
            return {**_result(operation="execution_reject", mirrored=False, reason="legacy_only"), "state": mission.state.value}
        if phase == "approve":
            if mission.state is MissionState.READY_TO_EXECUTE:
                mission = repo.dispatch(StartExecution(), idempotency_key=f"execution-start:{execution_id}")
            if mission.state is MissionState.EXECUTING:
                mission = repo.dispatch(MarkDiffReady(), idempotency_key=f"diff-ready:{execution_id}")
            if mission.state is MissionState.AWAITING_DIFF_DECISION:
                mission = repo.dispatch(ApproveDiff(), idempotency_key=f"diff-approve:{execution_id}")
            commit_sha = str((execution.get("merge") or {}).get("commit_sha") or execution.get("commit_sha") or "")
            if mission.state is MissionState.VERIFYING and mission.merged_commit_sha is None and commit_sha:
                mission = repo.dispatch(RecordMerge(commit_sha), idempotency_key=f"merge:{execution_id}:{commit_sha}")
        elif phase == "merge":
            commit_sha = str((execution.get("merge") or {}).get("commit_sha") or execution.get("commit_sha") or "")
            if mission.state is MissionState.AWAITING_DIFF_DECISION:
                mission = repo.dispatch(ApproveDiff(), idempotency_key=f"diff-approve:{execution_id}")
            if mission.state is MissionState.VERIFYING and commit_sha:
                mission = repo.dispatch(RecordMerge(commit_sha), idempotency_key=f"merge:{execution_id}:{commit_sha}")
        else:
            commit_sha = str((execution.get("merge") or {}).get("commit_sha") or execution.get("commit_sha") or "")
            if mission.state is MissionState.AWAITING_DIFF_DECISION:
                mission = repo.dispatch(ApproveDiff(), idempotency_key=f"diff-approve:{execution_id}")
            if mission.state is MissionState.VERIFYING and mission.merged_commit_sha is None and commit_sha:
                mission = repo.dispatch(RecordMerge(commit_sha), idempotency_key=f"merge:{execution_id}:{commit_sha}")
            repair_history_raw = execution.get("repair_history")
            repair_history = [row for row in repair_history_raw if isinstance(row, dict)] if isinstance(repair_history_raw, list) else []
            for repair in repair_history:
                attempt = int(repair.get("attempt") or 0)
                before_raw = repair.get("oracle_before")
                before: dict[str, Any] = before_raw if isinstance(before_raw, dict) else {}
                detail = str(before.get("detail") or repair.get("detail") or "repair attempt")
                if mission.state is MissionState.VERIFYING:
                    mission = repo.dispatch(
                        RecordOracle(OracleVerdict.FAIL, detail),
                        idempotency_key=f"oracle-fail:{execution_id}:{attempt}:{detail}",
                    )
                if mission.state is MissionState.REPAIRING:
                    mission = repo.dispatch(MarkDiffReady(), idempotency_key=f"repair-diff-ready:{execution_id}:{attempt}")
                if mission.state is MissionState.AWAITING_DIFF_DECISION:
                    mission = repo.dispatch(ApproveDiff(), idempotency_key=f"repair-diff-approve:{execution_id}:{attempt}")
                repair_merge_raw = repair.get("merge")
                repair_merge: dict[str, Any] = repair_merge_raw if isinstance(repair_merge_raw, dict) else {}
                repair_sha = str(repair_merge.get("commit_sha") or repair.get("exec_commit_sha") or "")
                if mission.state is MissionState.VERIFYING and mission.merged_commit_sha is None:
                    if not repair_sha:
                        return _result(operation="execution_oracle", mirrored=False, reason="repair_commit_missing")
                    mission = repo.dispatch(
                        RecordMerge(repair_sha),
                        idempotency_key=f"repair-merge:{execution_id}:{attempt}:{repair_sha}",
                    )
            if mission.state is MissionState.VERIFYING:
                oracle_raw = execution.get("oracle")
                oracle: dict[str, Any] = oracle_raw if isinstance(oracle_raw, dict) else {}
                verdict = OracleVerdict.PASS if str(oracle.get("verdict") or "").lower() == "pass" else OracleVerdict.FAIL
                detail = str(oracle.get("detail") or oracle.get("reason") or "")
                mission = repo.dispatch(RecordOracle(verdict, detail), idempotency_key=f"oracle:{execution_id}:{verdict.value}:{detail}")
    except (MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation=f"execution_{phase}", mirrored=False, reason=str(exc)[:240])
    return {**_result(operation=f"execution_{phase}", mirrored=True), "state": mission.state.value, "version": mission.version}
