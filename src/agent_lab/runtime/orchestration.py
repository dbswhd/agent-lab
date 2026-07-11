"""Unified orchestration read model — plan substate + mission phase (dual FSM slice A)."""

from __future__ import annotations

from typing import Any, TypedDict

from pathlib import Path

from agent_lab.run.state import RunStateLike

_PLAN_CLARIFY = frozenset({"INTAKE", "CLARIFY"})
_PLAN_DISCUSS = frozenset({"DRAFT", "PEER_REVIEW", "REFINE"})
_PLAN_GATE = frozenset({"HUMAN_PENDING"})
_PLAN_DONE = frozenset({"APPROVED"})

_EXECUTE_MISSION_PHASES = frozenset(
    {
        "EXECUTE_QUEUE",
        "DRY_RUN",
        "MERGE_REVIEW",
        "VERIFY",
        "REPAIR",
        "MISSION_DONE",
        "MISSION_PAUSED",
    }
)

# When mission is enabled, plan_workflow.phase should fall in this bucket per mission phase.
_MISSION_PLAN_BUCKETS: dict[str, frozenset[str]] = {
    "MISSION_DEFINE": _PLAN_CLARIFY,
    "CLARIFY": _PLAN_CLARIFY,
    "DISCUSS": _PLAN_DISCUSS | _PLAN_GATE,
    "PLAN_GATE": _PLAN_GATE | _PLAN_DISCUSS,
    "PLAN_REJECT": _PLAN_DISCUSS | _PLAN_GATE,
    "EXECUTE_QUEUE": _PLAN_DONE,
    "DRY_RUN": _PLAN_DONE,
    "MERGE_REVIEW": _PLAN_DONE,
    "VERIFY": _PLAN_DONE,
    "REPAIR": _PLAN_DONE,
    "MISSION_DONE": _PLAN_DONE,
    "MISSION_PAUSED": _PLAN_DONE | _PLAN_GATE | _PLAN_DISCUSS | _PLAN_CLARIFY,
}


class OrchestrationState(TypedDict):
    phase: str
    plan_substate: str | None
    mission_phase: str | None
    mission_enabled: bool
    phase_drift: bool
    phase_drift_reason: str | None
    reconcile_hint: str | None


def plan_substate_to_orchestration_phase(plan_phase: str | None) -> str:
    """Map plan_workflow.phase to mission-shaped orchestration phase."""
    phase = str(plan_phase or "INTAKE").strip().upper()
    if phase in _PLAN_CLARIFY:
        return "CLARIFY"
    if phase in _PLAN_DISCUSS:
        return "DISCUSS"
    if phase in _PLAN_GATE:
        return "PLAN_GATE"
    if phase in _PLAN_DONE:
        return "EXECUTE_QUEUE"
    return "MISSION_DEFINE"


def detect_phase_drift(run: RunStateLike) -> str | None:
    """Return a drift reason when plan_workflow and mission_loop disagree."""
    from agent_lab.mission.loop import get_mission_loop
    from agent_lab.plan.workflow_state import is_plan_workflow_active, plan_workflow_phase

    if not is_plan_workflow_active(run):
        return None

    plan_phase = plan_workflow_phase(run).upper()
    mission = get_mission_loop(run)
    if not mission.get("enabled"):
        return None

    mission_phase = str(mission.get("phase") or "MISSION_DEFINE").upper()

    if plan_phase == "APPROVED":
        if mission_phase in {"MISSION_DEFINE", "CLARIFY", "DISCUSS", "PLAN_GATE", "PLAN_REJECT"}:
            return f"plan_approved_vs_mission_{mission_phase.lower()}"
        return None

    allowed = _MISSION_PLAN_BUCKETS.get(mission_phase)
    if allowed is None:
        return None
    if plan_phase not in allowed:
        return f"plan_substate_{plan_phase.lower()}_vs_mission_{mission_phase.lower()}"
    return None


def reconcile_hint_for_drift(
    drift_reason: str | None,
    *,
    plan_substate: str | None,
    mission_phase: str | None,
) -> str | None:
    """Suggest which lane should catch up when plan substate and mission phase drift."""
    if not drift_reason:
        return None
    plan = str(plan_substate or "").upper()
    mission = str(mission_phase or "").upper()
    if drift_reason.startswith("plan_approved_vs_mission_"):
        return "advance_mission_past_plan_gate"
    if plan in _PLAN_CLARIFY and mission in {"DISCUSS", "PLAN_GATE"}:
        return "advance_plan_substate_or_rewind_mission_to_clarify"
    if plan in _PLAN_DONE and mission in {"MISSION_DEFINE", "CLARIFY", "DISCUSS", "PLAN_GATE", "PLAN_REJECT"}:
        return "advance_mission_to_execute_queue"
    if plan in _PLAN_DISCUSS | _PLAN_GATE and mission in _EXECUTE_MISSION_PHASES:
        return "approve_plan_or_align_mission_to_discuss"
    return "align_plan_substate_with_mission_phase"


def derive_orchestration_state(run: RunStateLike) -> OrchestrationState:
    """Single read-model for orchestration phase authority."""
    from agent_lab.mission.loop import get_mission_loop
    from agent_lab.plan.workflow_state import is_plan_workflow_active, plan_workflow_phase

    plan_substate: str | None = None
    if is_plan_workflow_active(run):
        plan_substate = plan_workflow_phase(run).upper()

    mission = get_mission_loop(run)
    mission_enabled = bool(mission.get("enabled"))
    mission_phase = str(mission.get("phase") or "MISSION_DEFINE").upper() if mission_enabled else None

    if mission_enabled and mission_phase:
        primary = mission_phase
    elif plan_substate:
        primary = plan_substate_to_orchestration_phase(plan_substate)
    else:
        primary = "MISSION_DEFINE"

    drift_reason = detect_phase_drift(run)
    return {
        "phase": primary,
        "plan_substate": plan_substate,
        "mission_phase": mission_phase,
        "mission_enabled": mission_enabled,
        "phase_drift": drift_reason is not None,
        "phase_drift_reason": drift_reason,
        "reconcile_hint": reconcile_hint_for_drift(
            drift_reason,
            plan_substate=plan_substate,
            mission_phase=mission_phase,
        ),
    }


def stamp_orchestration_state(run: dict[str, Any]) -> dict[str, Any]:
    """Persist derived orchestration snapshot on run.json (observability)."""
    orch = derive_orchestration_state(run)
    if orch["phase_drift"] and orch.get("phase_drift_reason"):
        orch = dict(orch)
        orch["alert"] = orch["phase_drift_reason"]
    run["orchestration"] = orch
    return run


def stamp_orchestration_on_folder(folder: Path) -> OrchestrationState:
    """Patch run.json orchestration snapshot and emit drift control span when needed."""
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    stamped: dict[str, Any] = {}

    def _stamp(run: dict[str, Any]) -> dict[str, Any]:
        updated = stamp_orchestration_state(run)
        stamped.update(updated.get("orchestration") or {})
        return updated

    patch_run_meta(folder, _stamp)
    orch = stamped if stamped else derive_orchestration_state(read_run_meta(folder))
    if orch.get("phase_drift"):
        try:
            from agent_lab.runtime.orchestration_reconcile import maybe_reconcile_orchestration_drift

            reconcile_out = maybe_reconcile_orchestration_drift(folder, orch=orch)
            if reconcile_out and reconcile_out.get("applied"):
                run_after = read_run_meta(folder)
                orch = derive_orchestration_state(run_after)
                stamped.update(orch)
        except Exception:
            pass
    if orch.get("phase_drift"):
        try:
            from agent_lab.trace_recorder import record_control_span

            record_control_span(
                folder,
                name="orchestration_phase_drift",
                status="alert",
                data={
                    "reason": orch.get("phase_drift_reason"),
                    "phase": orch.get("phase"),
                    "plan_substate": orch.get("plan_substate"),
                    "mission_phase": orch.get("mission_phase"),
                    "reconcile_hint": orch.get("reconcile_hint"),
                },
            )
        except Exception:
            pass
    return orch  # type: ignore[return-value]


def orchestration_work_phase(
    orchestration: OrchestrationState,
    *,
    has_plan: bool,
    has_pending_execution: bool,
    has_dry_run_diff: bool,
    pending_agreement: bool,
    latest_execution: dict[str, Any] | None,
    resume_phase: str | None = None,
) -> str:
    """Map unified orchestration state to Work tab phase."""
    from agent_lab.runtime.work_phase import resolve_work_phase_from_mission, resolve_work_phase_standalone

    plan_sub = str(orchestration.get("plan_substate") or "").upper()
    if plan_sub == "HUMAN_PENDING":
        return "review_needed"
    if plan_sub == "APPROVED":
        return "execute_pending"

    phase = str(orchestration.get("phase") or "MISSION_DEFINE").upper()
    if orchestration.get("mission_enabled"):
        mapped = resolve_work_phase_from_mission(phase, resume_phase=resume_phase)
        if mapped is not None:
            return mapped

    if phase == "MISSION_DONE":
        return "done"
    if phase in {"MERGE_REVIEW", "PLAN_REJECT"}:
        return "review_needed"
    if phase == "VERIFY":
        return "merge_verify"
    if phase in {"EXECUTE_QUEUE", "DRY_RUN", "REPAIR"}:
        return "execute_pending"
    if phase in {"CLARIFY", "DISCUSS", "PLAN_GATE", "MISSION_DEFINE"}:
        return "plan_draft"

    return resolve_work_phase_standalone(
        has_plan=has_plan,
        has_pending_execution=has_pending_execution,
        has_dry_run_diff=has_dry_run_diff,
        pending_agreement=pending_agreement,
        latest_execution=latest_execution,
    )
