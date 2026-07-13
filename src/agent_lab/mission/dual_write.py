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


def plan_write_authority_enabled(folder: Path | None = None) -> bool:
    """Soft retire slice 1: Mission journal owns plan phase writes.

    Requires dual-write (incl. optional session cohort). Authority without the
    bridge is a hard no — callers must fall back to legacy-first approve/reject.
    """
    if not is_truthy(os.getenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY")):
        return False
    return dual_write_enabled(folder)


def inbox_write_authority_enabled(folder: Path | None = None) -> bool:
    """Soft retire slice 2: Mission journal owns execution-gate open/close.

    Requires dual-write. Legacy ``human_inbox`` remains the UI/compatibility store.
    """
    if not is_truthy(os.getenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY")):
        return False
    return dual_write_enabled(folder)


def execution_write_authority_enabled(folder: Path | None = None) -> bool:
    """Soft retire slice 3: Mission journal must record execute/merge/oracle transitions.

    Requires dual-write. Legacy writers still perform side effects first; this flag
    fail-closes the HTTP route when the Mission commit does not mirror.
    """
    if not is_truthy(os.getenv("AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY")):
        return False
    return dual_write_enabled(folder)


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


def _merge_conflict_inbox_items(folder: Path) -> list[dict[str, Any]]:
    from agent_lab.human_inbox import pending_inbox_items

    items: list[dict[str, Any]] = []
    for item in pending_inbox_items(read_run_meta(folder)):
        source = str(item.get("source") or "")
        summary = str(item.get("summary") or "").lower()
        prompt = str(item.get("prompt") or "").lower()
        if source == "mission_circuit_break":
            items.append(item)
            continue
        if "merge conflict" in summary or "merge conflict" in prompt:
            items.append(item)
            continue
        if "structural execution failure" in summary or "structural execution failure" in prompt:
            items.append(item)
    return items


def _ensure_merge_conflict_gates(folder: Path) -> list[str]:
    """Mirror OpenExecutionGate for pending merge-conflict inbox items."""
    opened: list[str] = []
    for item in _merge_conflict_inbox_items(folder):
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        result = mirror_inbox_creation(
            folder,
            item_id=item_id,
            kind=str(item.get("kind") or "question"),
            reason=str(item.get("summary") or item.get("prompt") or "merge conflict"),
        )
        if result.get("mirrored") is True:
            opened.append(item_id)
    return opened


def _resolve_merge_conflict_inboxes(folder: Path) -> dict[str, Any]:
    """After merge/confirm, resolve legacy inbox items and close all related gates."""
    from agent_lab.human_inbox import pending_inbox_items, resolve_inbox_item
    from agent_lab.mission.application import MissionApplication

    closed: list[str] = []
    errors: list[str] = []
    targets: dict[str, dict[str, Any]] = {
        str(item.get("id") or ""): item for item in _merge_conflict_inbox_items(folder) if item.get("id")
    }
    for item in pending_inbox_items(read_run_meta(folder)):
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        if item_id not in targets and str(item.get("source") or "") == "mission_circuit_break":
            targets[item_id] = item

    for item_id, _item in targets.items():
        try:
            resolve_inbox_item(folder, item_id, decision="merge_confirmed", append_chat=False)
        except (ValueError, OSError):
            pass
        result = mirror_inbox_resolution(folder, item_id=item_id, answer="merge_confirmed")
        if result.get("mirrored") is True:
            closed.append(item_id)
        else:
            errors.append(f"{item_id}:{result.get('reason') or 'not_mirrored'}")

    mission = MissionApplication(folder, _goal(folder)).load()
    for gate in mission.open_gates:
        gate_id = gate.gate_id
        if gate_id in closed:
            continue
        result = mirror_inbox_resolution(folder, item_id=gate_id, answer="merge_confirmed")
        if result.get("mirrored") is True:
            closed.append(gate_id)
        else:
            errors.append(f"{gate_id}:{result.get('reason') or 'not_mirrored'}")
    try:
        from agent_lab.mission.loop import clear_circuit_breaker, get_mission_loop

        run = read_run_meta(folder)
        if get_mission_loop(run).get("circuit_breaker"):
            clear_circuit_breaker(folder, resume_phase="EXECUTE_QUEUE")
    except (OSError, ValueError):
        pass
    return {"closed_item_ids": closed, "errors": errors}


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
def commit_plan_approval(folder: Path, *, goal: str | None = None) -> dict[str, Any]:
    """Authority path: Mission journal is the plan-phase write source, then projects.

    Unlike ``mirror_plan_approval``, this requires
    ``plan_write_authority_enabled`` and returns ``mirrored=False`` with an
    explicit reason when the soft-retire flag/cohort gate is closed.
    """
    if not plan_write_authority_enabled(folder):
        return {
            "enabled": dual_write_enabled(folder),
            "operation": "plan_approve_commit",
            "mirrored": False,
            "reason": "plan_write_authority_disabled",
        }
    try:
        mission = MissionApplication(folder, _goal(folder, goal)).approve_plan()
    except (MissionApplicationError, MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="plan_approve_commit", mirrored=False, reason=str(exc)[:240])
    return {
        **_result(operation="plan_approve_commit", mirrored=True),
        "state": mission.state.value,
        "version": mission.version,
    }


@_observed
def commit_plan_rejection(
    folder: Path,
    *,
    note: str = "",
    goal: str | None = None,
    target_phase: str = "CLARIFY",
) -> dict[str, Any]:
    """Authority path reject: Mission owns phase; honors CLARIFY|REFINE|DRAFT projection."""
    if not plan_write_authority_enabled(folder):
        return {
            "enabled": dual_write_enabled(folder),
            "operation": "plan_reject_commit",
            "mirrored": False,
            "reason": "plan_write_authority_disabled",
        }
    try:
        mission = MissionApplication(folder, _goal(folder, goal)).reject_plan(note, target_phase=target_phase)
    except (MissionApplicationError, MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="plan_reject_commit", mirrored=False, reason=str(exc)[:240])
    return {
        **_result(operation="plan_reject_commit", mirrored=True),
        "state": mission.state.value,
        "version": mission.version,
    }


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


def _dispatch_open_gate(folder: Path, *, item_id: str, kind: str, reason: str) -> Any:
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    repo = MissionRepository(journal, folder.name, _goal(folder))
    return repo.dispatch(OpenExecutionGate(item_id, kind, reason), idempotency_key=f"gate-open:{item_id}")


def _dispatch_close_gate(folder: Path, *, item_id: str, answer: str = "") -> Any:
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    repo = MissionRepository(journal, folder.name, _goal(folder))
    mission = repo.load()
    if mission.state is MissionState.AWAITING_HUMAN:
        mission = repo.dispatch(ResolveBlock(), idempotency_key=f"inbox-resolve:{item_id}:{answer.strip()}")
    return repo.dispatch(CloseExecutionGate(item_id), idempotency_key=f"gate-close:{item_id}")


@_observed
def commit_inbox_creation(folder: Path, *, item_id: str, kind: str = "", reason: str = "") -> dict[str, Any]:
    """Authority path: OpenExecutionGate first (may bootstrap journal)."""
    if not inbox_write_authority_enabled(folder):
        return {
            "enabled": dual_write_enabled(folder),
            "operation": "inbox_create_commit",
            "mirrored": False,
            "reason": "inbox_write_authority_disabled",
        }
    try:
        mission = _dispatch_open_gate(folder, item_id=item_id, kind=kind, reason=reason)
    except (MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="inbox_create_commit", mirrored=False, reason=str(exc)[:240])
    return {
        **_result(operation="inbox_create_commit", mirrored=True),
        "state": mission.state.value,
        "open_gate_count": len(mission.open_gates),
    }


@_observed
def commit_inbox_resolution(folder: Path, *, item_id: str, answer: str = "") -> dict[str, Any]:
    """Authority path: CloseExecutionGate first (optional ResolveBlock)."""
    if not inbox_write_authority_enabled(folder):
        return {
            "enabled": dual_write_enabled(folder),
            "operation": "inbox_resolve_commit",
            "mirrored": False,
            "reason": "inbox_write_authority_disabled",
        }
    try:
        mission = _dispatch_close_gate(folder, item_id=item_id, answer=answer)
    except (MissionTransitionError, OSError, ValueError) as exc:
        return _result(operation="inbox_resolve_commit", mirrored=False, reason=str(exc)[:240])
    return {
        **_result(operation="inbox_resolve_commit", mirrored=True),
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
    return _execution_transition(folder, execution=execution, phase=phase, operation=f"execution_{phase}")


@_observed
def commit_execution_transition(
    folder: Path,
    *,
    execution: dict[str, Any],
    phase: Literal["approve", "reject", "merge", "oracle"],
) -> dict[str, Any]:
    """Authority path: same Mission recording as mirror, fail-closed at the route."""
    if not execution_write_authority_enabled(folder):
        return {
            "enabled": dual_write_enabled(folder),
            "operation": f"execution_{phase}_commit",
            "mirrored": False,
            "reason": "execution_write_authority_disabled",
        }
    blocked = _blocked_result(folder, f"execution_{phase}_commit")
    if blocked is not None:
        return {**blocked, "operation": f"execution_{phase}_commit"}
    return _execution_transition(
        folder,
        execution=execution,
        phase=phase,
        operation=f"execution_{phase}_commit",
    )


def sync_open_gates_for_inbox_items(
    folder: Path,
    items: list[dict[str, Any]],
    *,
    reason: str = "harvest",
) -> list[str]:
    """Open Mission execution gates for harvested/appended inbox items.

    Fail-open: individual mirror/commit failures are skipped so turn persistence
    is never blocked. Necessary for dual-write parity when items bypass
    ``create_inbox_item``.
    """
    opened: list[str] = []
    if not dual_write_enabled(folder):
        return opened
    for item in items:
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        kind = str(item.get("kind") or "question")
        item_reason = str(item.get("summary") or item.get("prompt") or reason)
        try:
            if inbox_write_authority_enabled(folder):
                result = commit_inbox_creation(folder, item_id=item_id, kind=kind, reason=item_reason)
            else:
                result = mirror_inbox_creation(folder, item_id=item_id, kind=kind, reason=item_reason)
        except Exception:
            continue
        if result.get("mirrored") is True:
            opened.append(item_id)
    return opened


def close_gates_for_inbox_ids(folder: Path, item_ids: list[str], *, answer: str = "superseded") -> list[str]:
    """Close Mission gates for superseded (or otherwise retired) inbox ids."""
    closed: list[str] = []
    if not dual_write_enabled(folder):
        return closed
    for item_id in item_ids:
        if not item_id:
            continue
        try:
            if inbox_write_authority_enabled(folder):
                result = commit_inbox_resolution(folder, item_id=item_id, answer=answer)
            else:
                result = mirror_inbox_resolution(folder, item_id=item_id, answer=answer)
        except Exception:
            continue
        if result.get("mirrored") is True:
            closed.append(item_id)
    return closed


def _execution_transition(
    folder: Path,
    *,
    execution: dict[str, Any],
    phase: Literal["approve", "reject", "merge", "oracle"],
    operation: str,
) -> dict[str, Any]:
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal.is_file():
        return _result(operation=operation, mirrored=False, reason="mission_journal_missing")
    repo = MissionRepository(journal, folder.name, _goal(folder))
    mission = repo.load()
    execution_id = str(execution.get("id") or execution.get("execution_id") or "unknown")
    execution_status = str(execution.get("status") or "")
    merge_conflict_inbox: dict[str, Any] | None = None
    try:
        if phase == "reject":
            return {
                **_result(operation=operation, mirrored=False, reason="legacy_only"),
                "state": mission.state.value,
            }
        if phase == "approve":
            if execution_status == "merge_conflict":
                merge_conflict_inbox = {
                    "opened_gate_ids": _ensure_merge_conflict_gates(folder),
                }
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
            if execution_status == "merged" and commit_sha:
                merge_conflict_inbox = _resolve_merge_conflict_inboxes(folder)
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
                        return _result(operation=operation, mirrored=False, reason="repair_commit_missing")
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
        return _result(operation=operation, mirrored=False, reason=str(exc)[:240])
    payload: dict[str, Any] = {
        **_result(operation=operation, mirrored=True),
        "state": mission.state.value,
        "version": mission.version,
    }
    if merge_conflict_inbox is not None:
        payload["merge_conflict_inbox"] = merge_conflict_inbox
    return payload
