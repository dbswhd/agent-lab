from __future__ import annotations

from agent_lab.runtime.orchestration import (
    derive_orchestration_state,
    detect_phase_drift,
    plan_substate_to_orchestration_phase,
)


def test_plan_substate_maps_to_orchestration_phase() -> None:
    assert plan_substate_to_orchestration_phase("CLARIFY") == "CLARIFY"
    assert plan_substate_to_orchestration_phase("DRAFT") == "DISCUSS"
    assert plan_substate_to_orchestration_phase("HUMAN_PENDING") == "PLAN_GATE"
    assert plan_substate_to_orchestration_phase("APPROVED") == "EXECUTE_QUEUE"


def test_orchestration_primary_from_plan_when_mission_disabled() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "DRAFT"},
        "mission_loop": {"enabled": False, "phase": "MISSION_DEFINE"},
    }
    orch = derive_orchestration_state(run)
    assert orch["phase"] == "DISCUSS"
    assert orch["plan_substate"] == "DRAFT"
    assert orch["phase_drift"] is False


def test_orchestration_primary_from_mission_when_enabled() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "APPROVED"},
        "mission_loop": {"enabled": True, "phase": "EXECUTE_QUEUE"},
    }
    orch = derive_orchestration_state(run)
    assert orch["phase"] == "EXECUTE_QUEUE"
    assert orch["plan_substate"] == "APPROVED"
    assert orch["phase_drift"] is False


def test_phase_drift_when_plan_clarify_mission_discuss() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "CLARIFY"},
        "mission_loop": {"enabled": True, "phase": "DISCUSS"},
    }
    reason = detect_phase_drift(run)
    assert reason == "plan_substate_clarify_vs_mission_discuss"
    orch = derive_orchestration_state(run)
    assert orch["phase_drift"] is True
    assert orch["phase_drift_reason"] == reason


def test_no_drift_when_plan_draft_mission_discuss() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "DRAFT"},
        "mission_loop": {"enabled": True, "phase": "DISCUSS"},
    }
    assert detect_phase_drift(run) is None
