"""Agent Lab unified runtime dispatcher (H2 execute lane write path)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.runtime.dispatch_result import DispatchResult
from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.discuss_lane import dispatch_discuss_event
from agent_lab.runtime.execute_lane import dispatch_execute_event
from agent_lab.runtime.mission_lane import dispatch_control_event, dispatch_mission_event
from agent_lab.run.meta import read_run_meta
from agent_lab.runtime.transitions import transition_entry_reason


def _record_runtime_dispatch_span(
    folder: Path,
    run: dict[str, Any],
    event: RuntimeEvent,
    *,
    phase: str,
    allowed: bool,
    reason: str,
    skipped: bool,
) -> None:
    try:
        from agent_lab.trace_recorder import record_control_span
        from agent_lab.room.turn_contract import contract_runtime_applied, turn_contract_mode

        data: dict[str, Any] = {
            "event": event.value,
            "phase": phase,
            "entry_reason": reason,
            "skipped": skipped,
        }
        contract = run.get("turn_contract")
        if isinstance(contract, dict) and contract:
            mode = turn_contract_mode()
            data["turn_contract_mode"] = mode
            data["turn_contract_id"] = contract.get("contract_id")
            data["turn_contract_source"] = contract.get("source")
            data["turn_contract_runtime_applied"] = contract_runtime_applied(mode, contract)
        record_control_span(
            folder,
            name="runtime_dispatch",
            status="skipped" if (not allowed or skipped) else "ok",
            data=data,
        )
    except Exception:
        pass


def dispatch(
    folder: Path,
    event: RuntimeEvent | str,
    payload: dict[str, Any] | None = None,
) -> DispatchResult:
    """Route a runtime event to the appropriate lane handler."""
    if isinstance(event, str):
        event = RuntimeEvent(event)
    run = read_run_meta(folder)
    allowed, reason, phase, _rows = transition_entry_reason(run, event, payload)
    if not allowed:
        result = DispatchResult(
            handled=True,
            skipped=True,
            reason=reason,
            phase=phase,
            extra={"event": event.value, "phase": phase},
        )
        _record_runtime_dispatch_span(
            folder,
            run,
            event,
            phase=phase,
            allowed=False,
            reason=reason,
            skipped=True,
        )
        return result
    if event.value.startswith("execute."):
        result = dispatch_execute_event(folder, event, payload)
    elif event.value.startswith("scribe.") or event.value.startswith("turn."):
        result = dispatch_discuss_event(folder, event, payload)
    elif event.value.startswith("mission."):
        result = dispatch_mission_event(folder, event, payload)
    elif event.value.startswith("plan."):
        from agent_lab.runtime.plan_lane import dispatch_plan_event

        result = dispatch_plan_event(folder, event, payload)
    elif event == RuntimeEvent.RUN_CANCEL:
        result = dispatch_control_event(folder, event, payload)
    else:
        result = DispatchResult(handled=False, reason=f"no handler for {event.value}")
    _record_runtime_dispatch_span(
        folder,
        run,
        event,
        phase=str(result.phase or phase),
        allowed=True,
        reason=reason,
        skipped=bool(result.skipped),
    )
    return result


def dispatch_verify_result(
    folder: Path,
    *,
    action_index: int,
    verdict: str,
    reason: str = "",
    oracle: dict[str, Any] | None = None,
) -> DispatchResult:
    """Convenience wrapper for merge-time Oracle verdict."""
    verdict_norm = str(verdict or "").strip().lower()
    event = RuntimeEvent.EXECUTE_VERIFY_PASS if verdict_norm == "pass" else RuntimeEvent.EXECUTE_VERIFY_FAIL
    return dispatch(
        folder,
        event,
        {
            "action_index": action_index,
            "verdict": verdict_norm,
            "reason": reason,
            "oracle": oracle,
        },
    )


def dispatch_prepare_verify(folder: Path, *, execution_id: str) -> DispatchResult:
    """Enter VERIFY through canonical transitions before recording an oracle verdict."""
    from agent_lab.core.mission_loop import get_mission_loop

    phase = str(get_mission_loop(read_run_meta(folder)).get("phase") or "")
    if phase == "MERGE_REVIEW":
        return dispatch(
            folder,
            RuntimeEvent.EXECUTE_MERGE_APPROVED,
            {"execution_id": execution_id},
        )
    if phase == "REPAIR":
        return dispatch(
            folder,
            RuntimeEvent.EXECUTE_REPAIR_VERIFY,
            {"execution_id": execution_id},
        )
    if phase == "VERIFY":
        return DispatchResult(handled=True, skipped=True, reason="already_verify", phase=phase)
    return DispatchResult(
        handled=True,
        skipped=True,
        reason="invalid_prepare_phase",
        phase=phase,
        extra={"execution_id": execution_id},
    )
