from __future__ import annotations

from agent_lab.mission.kernel import MissionState, PlanApproved, PlanRejected, PlanOpened, apply_event, new_mission
from agent_lab.mission.plan_bridge import PlanApprovalDecision, plan_decision_events


def test_plan_bridge_approval_binds_content_hash() -> None:
    mission = new_mission("m-1", "refactor auth")
    events = plan_decision_events(mission, "# Plan\n\nfix auth\n", PlanApprovalDecision(approved=True))
    assert isinstance(events[0], PlanOpened)
    assert isinstance(events[1], PlanApproved)
    current = mission
    for event in events:
        current = apply_event(current, event)
    assert current.state is MissionState.READY_TO_EXECUTE
    assert current.approved_plan_hash == events[0].plan_hash


def test_plan_bridge_rejection_returns_to_drafting() -> None:
    mission = new_mission("m-1", "refactor auth")
    events = plan_decision_events(mission, "# Plan\n\nfix auth\n", PlanApprovalDecision(approved=False, note="missing test"))
    assert isinstance(events[-1], PlanRejected)
    current = mission
    for event in events:
        current = apply_event(current, event)
    assert current.state is MissionState.DRAFTING


def test_plan_bridge_reopens_rejected_revision_for_approval() -> None:
    mission = new_mission("m-1", "refactor auth")
    first = plan_decision_events(mission, "# Plan\n\nfix auth\n", PlanApprovalDecision(approved=False))
    for event in first:
        mission = apply_event(mission, event)
    reopened = plan_decision_events(mission, "# Plan\n\nfix auth\n", PlanApprovalDecision(approved=True))
    assert len(reopened) == 2
    assert isinstance(reopened[1], PlanApproved)
