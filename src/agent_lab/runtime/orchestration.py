"""Unified orchestration read model — plan substate + mission phase (dual FSM slice A)."""

from __future__ import annotations

from typing import Any, TypedDict

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
    }


def stamp_orchestration_state(run: dict[str, Any]) -> dict[str, Any]:
    """Persist derived orchestration snapshot on run.json (observability)."""
    run["orchestration"] = derive_orchestration_state(run)
    return run
