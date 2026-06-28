"""Mission lane handlers — FSM conductor (delegates to mission_loop)."""

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


def handle_mission_enable(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission.loop import enable_mission_loop

    ml = enable_mission_loop(
        folder,
        start_autonomous=bool(payload.get("start_autonomous", False)),
    )
    return DispatchResult(
        handled=True,
        result=ml,
        phase=str(ml.get("phase") or ""),
    )


def handle_mission_plan_gate(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission.loop import run_plan_gate

    plan_md = payload.get("plan_md")
    if not isinstance(plan_md, str):
        return DispatchResult(handled=False, reason="missing plan_md")
    result = run_plan_gate(folder, plan_md)
    if isinstance(result, dict) and result.get("skipped"):
        return _skipped(result)
    phase = str(result.get("phase") or "") if isinstance(result, dict) else ""
    return DispatchResult(handled=True, result=result, phase=phase)


def handle_mission_advance(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission.advance import maybe_advance_mission

    executor_raw = payload.get("executor")
    result = maybe_advance_mission(
        folder,
        permissions=payload.get("permissions") if isinstance(payload.get("permissions"), dict) else None,
        executor=str(executor_raw).strip() if executor_raw is not None else None,
    )
    if isinstance(result, dict) and result.get("skipped"):
        return _skipped(result)
    phase = str(result.get("phase") or "") if isinstance(result, dict) else ""
    return DispatchResult(handled=True, result=result, phase=phase)


def handle_mission_pause(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission.loop import pause_mission_loop

    result = pause_mission_loop(
        folder,
        reason=str(payload.get("reason") or "user_cancel"),
        cleanup_executions=bool(payload.get("cleanup_executions", True)),
    )
    if isinstance(result, dict) and result.get("skipped"):
        return _skipped(result)
    phase = str(result.get("phase") or "") if isinstance(result, dict) else ""
    return DispatchResult(handled=True, result=result, phase=phase)


def handle_mission_resume(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission.loop import resume_mission_loop

    resume_phase = payload.get("resume_phase")
    phase_arg = str(resume_phase).strip() if resume_phase is not None else None
    result = resume_mission_loop(folder, resume_phase=phase_arg or None)
    if isinstance(result, dict) and result.get("skipped"):
        return _skipped(result)
    phase = str(result.get("phase") or "") if isinstance(result, dict) else ""
    return DispatchResult(handled=True, result=result, phase=phase)


def handle_mission_circuit_breaker(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission.loop import trigger_circuit_breaker

    reason = str(payload.get("reason") or "").strip()
    if not reason:
        return DispatchResult(handled=False, reason="missing reason")
    inbox_prompt = payload.get("inbox_prompt")
    ml = trigger_circuit_breaker(
        folder,
        reason=reason,
        inbox_prompt=str(inbox_prompt).strip() if isinstance(inbox_prompt, str) and inbox_prompt.strip() else None,
    )
    return DispatchResult(
        handled=True,
        result=ml,
        phase=str(ml.get("phase") or ""),
    )


def handle_mission_circuit_clear(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission.loop import clear_circuit_breaker

    resume_phase = str(payload.get("resume_phase") or "DISCUSS").strip()
    ml = clear_circuit_breaker(folder, resume_phase=resume_phase)
    return DispatchResult(
        handled=True,
        result=ml,
        phase=str(ml.get("phase") or ""),
    )


def handle_mission_discuss_recovery(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission.loop import run_mission_discuss_recovery

    result = run_mission_discuss_recovery(
        folder,
        permissions=payload.get("permissions") if isinstance(payload.get("permissions"), dict) else None,
        on_event=payload.get("on_event"),
    )
    if isinstance(result, dict) and result.get("skipped"):
        return _skipped(result)
    phase = str(result.get("phase") or "") if isinstance(result, dict) else ""
    return DispatchResult(handled=True, result=result, phase=phase)


def handle_run_cancel(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission.loop import pause_mission_loop

    result = pause_mission_loop(
        folder,
        reason=str(payload.get("reason") or "global_cancel"),
        cleanup_executions=bool(payload.get("cleanup_executions", True)),
    )
    if isinstance(result, dict) and result.get("skipped"):
        return _skipped(result)
    phase = str(result.get("phase") or "") if isinstance(result, dict) else ""
    return DispatchResult(handled=True, result=result, phase=phase)


_MISSION_HANDLERS = {
    RuntimeEvent.MISSION_ENABLE: handle_mission_enable,
    RuntimeEvent.MISSION_PLAN_GATE: handle_mission_plan_gate,
    RuntimeEvent.MISSION_ADVANCE: handle_mission_advance,
    RuntimeEvent.MISSION_PAUSE: handle_mission_pause,
    RuntimeEvent.MISSION_RESUME: handle_mission_resume,
    RuntimeEvent.MISSION_CIRCUIT_BREAKER: handle_mission_circuit_breaker,
    RuntimeEvent.MISSION_CIRCUIT_CLEAR: handle_mission_circuit_clear,
    RuntimeEvent.MISSION_DISCUSS_RECOVERY: handle_mission_discuss_recovery,
}

_CONTROL_HANDLERS = {
    RuntimeEvent.RUN_CANCEL: handle_run_cancel,
}


def dispatch_mission_event(
    folder: Path,
    event: RuntimeEvent,
    payload: dict[str, Any] | None = None,
) -> DispatchResult:
    handler = _MISSION_HANDLERS.get(event)
    if handler is None:
        return DispatchResult(handled=False, reason=f"unsupported mission event: {event}")
    return handler(folder, payload or {})


def dispatch_control_event(
    folder: Path,
    event: RuntimeEvent,
    payload: dict[str, Any] | None = None,
) -> DispatchResult:
    handler = _CONTROL_HANDLERS.get(event)
    if handler is None:
        return DispatchResult(handled=False, reason=f"unsupported control event: {event}")
    return handler(folder, payload or {})
