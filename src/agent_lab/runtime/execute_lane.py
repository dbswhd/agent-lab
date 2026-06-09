"""Execute lane handlers — mission FSM side effects (delegates to mission_loop for now)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.runtime.dispatch_result import DispatchResult
from agent_lab.runtime.events import RuntimeEvent


def _skipped(result: Any) -> DispatchResult:
    if isinstance(result, dict) and result.get("skipped"):
        return DispatchResult(
            handled=True,
            skipped=True,
            reason=str(result.get("reason") or "skipped"),
            result=result,
        )
    return DispatchResult(handled=True, skipped=False, result=result)


def handle_execute_dry_run_start(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission_loop import set_execution_phase
    from agent_lab.run_meta import read_run_meta
    from agent_lab.runtime.policy import PolicyEngine

    run = read_run_meta(folder)
    snap = PolicyEngine.gate_snapshot(run)
    if snap.get("block_source") and not (snap.get("gates") or {}).get("execute", {}).get(
        "open", True
    ):
        return DispatchResult(
            handled=True,
            skipped=True,
            reason=str(snap.get("block_reason") or "execute blocked by policy"),
            phase=None,
            extra={"gate_snapshot": snap},
        )

    action_index = payload.get("action_index")
    if action_index is None:
        return DispatchResult(handled=False, reason="missing action_index")
    ml = set_execution_phase(
        folder,
        phase="DRY_RUN",
        current_action_index=int(action_index),
    )
    return DispatchResult(
        handled=True,
        result=ml,
        phase=str(ml.get("phase") or ""),
    )


def handle_execute_dry_run_complete(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission_loop import on_dry_run_complete

    execution = payload.get("execution")
    if not isinstance(execution, dict):
        return DispatchResult(handled=False, reason="missing execution")
    result = on_dry_run_complete(folder, execution)
    if result is None:
        return DispatchResult(handled=True, skipped=True, reason="mission_loop_disabled")
    return DispatchResult(
        handled=True,
        result=result,
        phase=str(result.get("phase") or ""),
    )


def handle_execute_dry_run_cancel(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission_loop import pause_mission_loop

    result = pause_mission_loop(
        folder,
        reason=str(payload.get("reason") or "dry_run_cancelled"),
        cleanup_executions=bool(payload.get("cleanup_executions", False)),
    )
    if result.get("skipped"):
        return _skipped(result)
    ml = result.get("mission_loop") if isinstance(result.get("mission_loop"), dict) else result
    phase = str(ml.get("phase") or "") if isinstance(ml, dict) else None
    return DispatchResult(handled=True, result=result, phase=phase)


def handle_execute_merge_approved(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission_loop import on_merge_confirm

    execution_id = str(payload.get("execution_id") or "").strip()
    if not execution_id:
        return DispatchResult(handled=False, reason="missing execution_id")
    result = on_merge_confirm(folder, execution_id=execution_id)
    if result is None:
        return DispatchResult(handled=True, skipped=True, reason="mission_loop_disabled")
    return DispatchResult(
        handled=True,
        result=result,
        phase=str(result.get("phase") or ""),
    )


def handle_execute_merge_rejected(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission_loop import on_merge_abort

    execution_id = str(payload.get("execution_id") or "").strip()
    if not execution_id:
        return DispatchResult(handled=False, reason="missing execution_id")
    result = on_merge_abort(folder, execution_id=execution_id)
    if result is None:
        return DispatchResult(handled=True, skipped=True, reason="mission_loop_disabled")
    return DispatchResult(
        handled=True,
        result=result,
        phase=str(result.get("phase") or ""),
    )


def handle_execute_verify_result(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission_loop import on_verify_result

    action_index = payload.get("action_index")
    if action_index is None:
        return DispatchResult(handled=False, reason="missing action_index")
    verdict = str(payload.get("verdict") or "").strip().lower()
    result = on_verify_result(
        folder,
        action_index=int(action_index),
        verdict=verdict,
        reason=str(payload.get("reason") or ""),
        oracle=payload.get("oracle") if isinstance(payload.get("oracle"), dict) else None,
    )
    if isinstance(result, dict) and result.get("skipped"):
        return _skipped(result)
    phase = str(result.get("phase") or "") if isinstance(result, dict) else None
    return DispatchResult(handled=True, result=result, phase=phase)


def handle_execute_structural_fail(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission_loop import on_structural_execution_failure

    reason = str(payload.get("reason") or "").strip()
    if not reason:
        return DispatchResult(handled=False, reason="missing reason")
    action_index = payload.get("action_index")
    idx = int(action_index) if action_index is not None else None
    result = on_structural_execution_failure(folder, reason=reason, action_index=idx)
    if result is None:
        return DispatchResult(handled=True, skipped=True, reason="mission_loop_disabled")
    return DispatchResult(
        handled=True,
        result=result,
        phase=str(result.get("phase") or ""),
    )


_EXECUTE_HANDLERS = {
    RuntimeEvent.EXECUTE_DRY_RUN_START: handle_execute_dry_run_start,
    RuntimeEvent.EXECUTE_DRY_RUN_COMPLETE: handle_execute_dry_run_complete,
    RuntimeEvent.EXECUTE_DRY_RUN_CANCEL: handle_execute_dry_run_cancel,
    RuntimeEvent.EXECUTE_MERGE_APPROVED: handle_execute_merge_approved,
    RuntimeEvent.EXECUTE_MERGE_REJECTED: handle_execute_merge_rejected,
    RuntimeEvent.EXECUTE_VERIFY_PASS: handle_execute_verify_result,
    RuntimeEvent.EXECUTE_VERIFY_FAIL: handle_execute_verify_result,
    RuntimeEvent.EXECUTE_STRUCTURAL_FAIL: handle_execute_structural_fail,
}


def dispatch_execute_event(
    folder: Path,
    event: RuntimeEvent,
    payload: dict[str, Any] | None = None,
) -> DispatchResult:
    handler = _EXECUTE_HANDLERS.get(event)
    if handler is None:
        return DispatchResult(handled=False, reason=f"unsupported execute event: {event}")
    return handler(folder, payload or {})
