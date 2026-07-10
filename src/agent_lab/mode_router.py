"""Autonomous mode router — CLARIFY / CONSENSUS / EXECUTE orchestration.

Classifies mission mode from run.json, records telemetry, and applies phase transitions
for the staged clarify → discuss → plan-gate path. Human approval gates (plan approve,
merge review) are never bypassed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from agent_lab.time_utils import utc_now_iso

Mode = Literal["CLARIFY", "CONSENSUS", "EXECUTE"]

_EXECUTE_PHASES = frozenset({"EXECUTE_QUEUE", "DRY_RUN", "MERGE_REVIEW", "VERIFY", "REPAIR"})
_CONSENSUS_PHASES = frozenset({"DISCUSS", "PLAN_GATE", "PLAN_REJECT"})
_MODE_ENTRY_PHASES = frozenset({"MISSION_DEFINE", "DISCUSS"})


def select_mode(run: dict[str, Any]) -> Mode:
    """Classify the mission's current pipeline mode from run signals (pure read)."""
    ml = run.get("mission_loop")
    ml = ml if isinstance(ml, dict) else {}
    phase = str(ml.get("phase") or "")
    if phase in _EXECUTE_PHASES:
        return "EXECUTE"
    if phase in _CONSENSUS_PHASES:
        return "CONSENSUS"
    from agent_lab.clarity import clarity_threshold_met

    return "CONSENSUS" if clarity_threshold_met(run) else "CLARIFY"


def resolve_mission_bootstrap_phase(run: dict[str, Any]) -> str:
    """Initial mission_loop phase after MISSION_DEFINE when goal is ready."""
    from agent_lab.plan.workflow import plan_workflow_completed_clarify

    if plan_workflow_completed_clarify(run):
        return "DISCUSS"
    from agent_lab.clarity import clarity_threshold_met

    return "DISCUSS" if clarity_threshold_met(run) else "CLARIFY"


def record_mode_route(folder: Any) -> dict[str, Any]:
    """Persist the current mode decision to run.json mission_loop.mode_route (observable)."""
    from agent_lab.mission.loop import get_mission_loop
    from agent_lab.run.meta import patch_run_meta

    captured: dict[str, Any] = {}

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        ml = get_mission_loop(run)
        mode = select_mode(run)
        route = {
            "mode": mode,
            "phase": ml.get("phase"),
            "at": utc_now_iso(),
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


def _enter_clarify_if_needed(folder: Path, run: dict[str, Any], phase: str) -> tuple[dict[str, Any], str]:
    """Auto-enter CLARIFY when clarity is unmet and plan_workflow does not own clarify."""
    from agent_lab.clarity import clarity_threshold_met
    from agent_lab.mission.loop import get_mission_loop
    from agent_lab.plan.workflow import plan_workflow_completed_clarify
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    if plan_workflow_completed_clarify(run) or clarity_threshold_met(run):
        return run, phase
    if phase not in _MODE_ENTRY_PHASES and phase != "CLARIFY":
        return run, phase

    def _enter(run_in: dict[str, Any]) -> dict[str, Any]:
        m = get_mission_loop(run_in)
        m["phase"] = "CLARIFY"
        run_in["mission_loop"] = m
        return run_in

    patch_run_meta(folder, _enter)
    run = read_run_meta(folder)
    return run, "CLARIFY"


def apply_mission_mode_route(folder: Path) -> dict[str, Any] | None:
    """Apply CLARIFY/CONSENSUS transitions from the active mode.

    Returns a result dict when this tick is fully handled (forwarded or waiting),
    or None when the caller should continue with execute/repair/verify phases.
    """
    from agent_lab.mission.loop import get_mission_loop
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    record_mode_route(folder)
    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return None

    phase = str(ml.get("phase") or "")
    if phase == "MISSION_DEFINE":
        from agent_lab.mission.loop import mission_define_ready

        if mission_define_ready(run):
            bootstrap = resolve_mission_bootstrap_phase(run)
            if bootstrap != phase:

                def _bootstrap(run_in: dict[str, Any]) -> dict[str, Any]:
                    m = get_mission_loop(run_in)
                    m["phase"] = bootstrap
                    run_in["mission_loop"] = m
                    return run_in

                patch_run_meta(folder, _bootstrap)
                run = read_run_meta(folder)
                phase = bootstrap

    run, phase = _enter_clarify_if_needed(folder, run, phase)
    ml = get_mission_loop(run)

    if phase == "CLARIFY":
        from agent_lab.clarity import clarity_threshold_met, ensure_clarify_questions, extract_established_facts

        extract_established_facts(folder)
        if not clarity_threshold_met(run):
            interview = ensure_clarify_questions(folder)
            pending_questions = (interview or {}).get("questions") if isinstance(interview, dict) else None
            return {
                "skipped": True,
                "reason": "clarity_pending",
                "phase": "CLARIFY",
                "questions": pending_questions,
            }

        def _clarify_to_discuss(run_in: dict[str, Any]) -> dict[str, Any]:
            m = get_mission_loop(run_in)
            m["phase"] = "DISCUSS"
            run_in["mission_loop"] = m
            return run_in

        patch_run_meta(folder, _clarify_to_discuss)
        return {"status": "forwarded", "phase": "DISCUSS", "reason": "clarity_met"}

    if phase == "DISCUSS":
        from agent_lab.consensus_gate import consensus_gate_met

        if not consensus_gate_met(run):
            return {"skipped": True, "reason": "consensus_pending", "phase": "DISCUSS"}

        def _to_plan(run_in: dict[str, Any]) -> dict[str, Any]:
            m = get_mission_loop(run_in)
            m["phase"] = "PLAN_GATE"
            run_in["mission_loop"] = m
            return run_in

        patch_run_meta(folder, _to_plan)
        ml_out = get_mission_loop(read_run_meta(folder))
        return {
            "status": "forwarded",
            "phase": ml_out.get("phase"),
        }

    return None


def resolve_active_phase(run: dict[str, Any]) -> str:
    """Active FSM phase for stage routing: plan_workflow phase when active, else mission_loop phase."""
    from agent_lab.plan.workflow import is_plan_workflow_active, plan_workflow_phase

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
    from agent_lab.mission.loop import get_mission_loop
    from agent_lab.run.meta import patch_run_meta

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        ml = get_mission_loop(run)
        ml["stage_route"] = {
            "phase": decision.get("phase"),
            "consensus_mode": bool(decision.get("consensus_mode")),
            "applied": bool(decision.get("applied")),
            "at": utc_now_iso(),
        }
        run["mission_loop"] = ml
        return run

    patch_run_meta(folder, _patch)
