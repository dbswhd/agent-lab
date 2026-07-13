from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from agent_lab.env_flags import is_truthy
from agent_lab.mission.application import MissionApplication, MissionApplicationError
from agent_lab.mission.kernel import (
    ApproveDiff,
    MarkDiffReady,
    MissionState,
    OracleVerdict,
    RecordMerge,
    RecordOracle,
    ResolveBlock,
    StartExecution,
)
from agent_lab.mission.errors import MissionTransitionError
from agent_lab.mission.repository import MissionRepository
from agent_lab.run.meta import read_run_meta


def dual_write_enabled() -> bool:
    return bool(is_truthy(os.getenv("AGENT_LAB_MISSION_DUAL_WRITE")))


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


def mirror_plan_approval(folder: Path, *, goal: str | None = None) -> dict[str, Any]:
    if not dual_write_enabled():
        return {"enabled": False, "operation": "plan_approve", "mirrored": False}
    try:
        mission = MissionApplication(folder, _goal(folder, goal)).approve_plan()
    except (MissionApplicationError, MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="plan_approve", mirrored=False, reason=str(exc)[:240])
    return {**_result(operation="plan_approve", mirrored=True), "state": mission.state.value, "version": mission.version}


def mirror_plan_rejection(folder: Path, *, note: str = "", goal: str | None = None) -> dict[str, Any]:
    if not dual_write_enabled():
        return {"enabled": False, "operation": "plan_reject", "mirrored": False}
    try:
        mission = MissionApplication(folder, _goal(folder, goal)).reject_plan(note)
    except (MissionApplicationError, MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="plan_reject", mirrored=False, reason=str(exc)[:240])
    return {**_result(operation="plan_reject", mirrored=True), "state": mission.state.value, "version": mission.version}


def mirror_inbox_resolution(folder: Path, *, item_id: str, answer: str = "") -> dict[str, Any]:
    if not dual_write_enabled():
        return {"enabled": False, "operation": "inbox_resolve", "mirrored": False}
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal.is_file():
        return _result(operation="inbox_resolve", mirrored=False, reason="mission_journal_missing")
    repo = MissionRepository(journal, folder.name, _goal(folder))
    mission = repo.load()
    if mission.state is not MissionState.AWAITING_HUMAN:
        return {**_result(operation="inbox_resolve", mirrored=False, reason="mission_not_awaiting_human"), "state": mission.state.value}
    try:
        mission = repo.dispatch(ResolveBlock(), idempotency_key=f"inbox-resolve:{item_id}:{answer.strip()}")
    except (MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="inbox_resolve", mirrored=False, reason=str(exc)[:240])
    return {**_result(operation="inbox_resolve", mirrored=True), "state": mission.state.value, "version": mission.version}


def mirror_execution_transition(
    folder: Path,
    *,
    execution: dict[str, Any],
    phase: Literal["approve", "reject", "merge", "oracle"],
) -> dict[str, Any]:
    if not dual_write_enabled():
        return {"enabled": False, "operation": f"execution_{phase}", "mirrored": False}
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
            if mission.state is MissionState.VERIFYING:
                oracle_raw = execution.get("oracle")
                oracle: dict[str, Any] = oracle_raw if isinstance(oracle_raw, dict) else {}
                verdict = OracleVerdict.PASS if str(oracle.get("verdict") or "").lower() == "pass" else OracleVerdict.FAIL
                detail = str(oracle.get("detail") or oracle.get("reason") or "")
                mission = repo.dispatch(RecordOracle(verdict, detail), idempotency_key=f"oracle:{execution_id}:{verdict.value}:{detail}")
    except (MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation=f"execution_{phase}", mirrored=False, reason=str(exc)[:240])
    return {**_result(operation=f"execution_{phase}", mirrored=True), "state": mission.state.value, "version": mission.version}
