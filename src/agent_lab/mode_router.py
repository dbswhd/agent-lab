"""Autonomous mode router for AGENT_LAB_PIPELINE.

Classifies the current mission into CLARIFY / CONSENSUS / EXECUTE from run.json signals and
records the decision to run.json (observable). The router only *classifies* — it never bypasses
Human approval gates (HITL preserved): EXECUTE classification still flows through the existing
plan-approval and merge-approval gates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

Mode = Literal["CLARIFY", "CONSENSUS", "EXECUTE"]

_EXECUTE_PHASES = frozenset({"EXECUTE_QUEUE", "DRY_RUN", "MERGE_REVIEW", "VERIFY", "REPAIR"})
_CONSENSUS_PHASES = frozenset({"DISCUSS", "PLAN_GATE", "PLAN_REJECT"})


def select_mode(run: dict[str, Any]) -> Mode:
    """Classify the mission's current pipeline mode from run signals (pure read)."""
    ml = run.get("mission_loop")
    ml = ml if isinstance(ml, dict) else {}
    phase = str(ml.get("phase") or "")
    if phase in _EXECUTE_PHASES:
        return "EXECUTE"
    if phase in _CONSENSUS_PHASES:
        return "CONSENSUS"
    # CLARIFY / MISSION_DEFINE / other pre-discuss: gate on clarity signals.
    from agent_lab.clarity import clarity_threshold_met

    return "CONSENSUS" if clarity_threshold_met(run) else "CLARIFY"


def record_mode_route(folder: Any) -> dict[str, Any]:
    """Persist the current mode decision to run.json mission_loop.mode_route (observable)."""
    from agent_lab.mission_loop import get_mission_loop
    from agent_lab.run_meta import patch_run_meta

    captured: dict[str, Any] = {}

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        ml = get_mission_loop(run)
        mode = select_mode(run)
        route = {
            "mode": mode,
            "phase": ml.get("phase"),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        ml["mode_route"] = route
        run["mission_loop"] = ml
        captured.update(route)
        return run

    patch_run_meta(folder, _patch)
    if captured:
        from agent_lab.goal_ledger import append_goal_event

        append_goal_event(
            folder,
            "mode_route",
            mode=captured.get("mode"),
            phase=captured.get("phase"),
            dedup_mode=True,
        )
    return captured


def resolve_active_phase(run: dict[str, Any]) -> str:
    """Active FSM phase for stage routing: plan_workflow phase when active, else mission_loop phase."""
    from agent_lab.plan_workflow import is_plan_workflow_active, plan_workflow_phase

    if is_plan_workflow_active(run):
        return plan_workflow_phase(run)
    ml = run.get("mission_loop") if isinstance(run, dict) else None
    return str((ml or {}).get("phase") or "") if isinstance(ml, dict) else ""


def record_routing_decision(folder: Any, decision: dict[str, Any]) -> None:
    """Persist a stage-routing decision to run.json mission_loop.stage_route (observational).

    Telemetry only: never affects fan-out. No-op without a folder so run_room's pre-bootstrap
    discuss turns stay byte-identical.
    """
    if not folder:
        return
    from agent_lab.mission_loop import get_mission_loop
    from agent_lab.run_meta import patch_run_meta

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        ml = get_mission_loop(run)
        ml["stage_route"] = {
            "phase": decision.get("phase"),
            "consensus_mode": bool(decision.get("consensus_mode")),
            "applied": bool(decision.get("applied")),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        run["mission_loop"] = ml
        return run

    patch_run_meta(folder, _patch)
