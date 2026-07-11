from __future__ import annotations

from agent_lab.plan.workflow_state import apply_plan_substate_patch
from agent_lab.runtime.orchestration import (
    orchestration_work_phase,
    stamp_orchestration_state,
)
from agent_lab.runtime.work_phase import resolve_work_phase


def test_apply_plan_substate_patch_stamps_orchestration() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "CLARIFY"},
        "mission_loop": {"enabled": False, "phase": "MISSION_DEFINE"},
    }
    updated = apply_plan_substate_patch(run, phase="DRAFT", clarify_round=1)
    assert updated["plan_workflow"]["phase"] == "DRAFT"
    assert updated["orchestration"]["plan_substate"] == "DRAFT"
    assert updated["orchestration"]["phase"] == "DISCUSS"


def test_stamp_orchestration_sets_alert_on_drift() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "CLARIFY"},
        "mission_loop": {"enabled": True, "phase": "DISCUSS"},
    }
    stamped = stamp_orchestration_state(run)
    assert stamped["orchestration"]["phase_drift"] is True
    assert stamped["orchestration"]["alert"] == "plan_substate_clarify_vs_mission_discuss"


def test_orchestration_work_phase_human_pending_overrides_mission() -> None:
    orch = {
        "phase": "DISCUSS",
        "plan_substate": "HUMAN_PENDING",
        "mission_phase": "DISCUSS",
        "mission_enabled": True,
        "phase_drift": False,
        "phase_drift_reason": None,
    }
    assert (
        orchestration_work_phase(
            orch,
            has_plan=True,
            has_pending_execution=False,
            has_dry_run_diff=False,
            pending_agreement=False,
            latest_execution=None,
        )
        == "review_needed"
    )


def test_resolve_work_phase_prefers_orchestration_when_run_given() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "APPROVED"},
        "mission_loop": {"enabled": True, "phase": "VERIFY"},
        "orchestration": {
            "phase": "VERIFY",
            "plan_substate": "APPROVED",
            "mission_phase": "VERIFY",
            "mission_enabled": True,
            "phase_drift": False,
            "phase_drift_reason": None,
        },
    }
    assert (
        resolve_work_phase(
            mission_enabled=True,
            mission_phase="VERIFY",
            resume_phase=None,
            plan_workflow_enabled=True,
            plan_workflow_phase="APPROVED",
            has_plan=True,
            has_pending_execution=False,
            has_dry_run_diff=False,
            pending_agreement=False,
            latest_execution=None,
            run=run,
        )
        == "execute_pending"
    )
