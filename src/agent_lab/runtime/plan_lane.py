"""Plan workflow lane — FSM tick/advance through runtime dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.runtime.dispatch_result import DispatchResult
from agent_lab.runtime.events import RuntimeEvent


def handle_plan_workflow_tick(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.plan.workflow_tick import _execute_plan_workflow_tick
    from agent_lab.runtime.orchestration import stamp_orchestration_on_folder

    result = _execute_plan_workflow_tick(
        folder,
        synthesize=bool(payload.get("synthesize")),
        cancelled=bool(payload.get("cancelled")),
        plan_md=str(payload.get("plan_md") or ""),
        plan_before=str(payload.get("plan_before") or ""),
        has_pending_inbox_question=bool(payload.get("has_pending_inbox_question")),
        turn_policy_advance=bool(payload.get("turn_policy_advance")),
    )

    stamp_orchestration_on_folder(folder)
    phase = str(result.get("phase") or "") if isinstance(result, dict) else None
    skipped = bool(isinstance(result, dict) and result.get("handled") is False)
    return DispatchResult(
        handled=True,
        skipped=skipped,
        result=result,
        phase=phase,
        reason=None if not skipped else str(result.get("reason") or "plan_tick_skipped"),
    )


def handle_plan_workflow_advance(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.inbox.mcp_policy import enforce_mcp_plan_phase_advance_policy
    from agent_lab.plan.workflow_state import (
        MCP_ADVANCE_TARGETS,
        PLAN_FSM_ORDER,
        plan_workflow_phase,
        set_plan_workflow_phase,
    )
    from agent_lab.room.turn_policy import stamp_pending_skill_intent, turn_policy_enabled
    from agent_lab.run.meta import read_run_meta
    from agent_lab.runtime.orchestration import stamp_orchestration_on_folder

    caller_agent = payload.get("caller_agent")
    enforce_mcp_plan_phase_advance_policy(folder, caller_agent=caller_agent if isinstance(caller_agent, str) else None)

    target = str(payload.get("target_phase") or "").strip().upper()
    if target not in MCP_ADVANCE_TARGETS:
        allowed = ", ".join(sorted(MCP_ADVANCE_TARGETS))
        return DispatchResult(handled=True, skipped=True, reason=f"invalid_target:{allowed}")

    run = read_run_meta(folder)
    current = plan_workflow_phase(run)
    order = list(PLAN_FSM_ORDER)
    if current not in order or target not in order:
        return DispatchResult(handled=True, skipped=True, reason="invalid_plan_workflow_phase")
    if order.index(target) <= order.index(current):
        return DispatchResult(handled=True, skipped=True, reason="forward_advance_only")

    set_plan_workflow_phase(folder, target)  # type: ignore[arg-type]
    if turn_policy_enabled() and target in {"DRAFT", "REFINE", "HUMAN_PENDING"}:
        stamp_pending_skill_intent(folder, "plan_draft")

    stamp_orchestration_on_folder(folder)

    body: dict[str, Any] = {
        "ok": True,
        "previous_phase": current,
        "phase": target,
    }
    reason = payload.get("reason")
    if isinstance(reason, str) and reason.strip():
        body["reason"] = reason.strip()[:500]
    return DispatchResult(handled=True, result=body, phase=target)


_PLAN_HANDLERS = {
    RuntimeEvent.PLAN_WORKFLOW_TICK: handle_plan_workflow_tick,
    RuntimeEvent.PLAN_WORKFLOW_ADVANCE: handle_plan_workflow_advance,
}


def dispatch_plan_event(
    folder: Path,
    event: RuntimeEvent,
    payload: dict[str, Any] | None = None,
) -> DispatchResult:
    handler = _PLAN_HANDLERS.get(event)
    if handler is None:
        return DispatchResult(handled=False, reason=f"unsupported plan event: {event}")
    return handler(folder, payload or {})
