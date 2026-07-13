from __future__ import annotations

from agent_lab.mission.activity import ActivityState, AwaitHuman, StartActivity, apply_activity_event, decide_activity, new_activity
from agent_lab.mission.decision_queue import AnswerDecision, apply_decision_event, decide_decision, new_decision
from agent_lab.mission.human_bridge import resolve_block, resume_activity
from agent_lab.mission.kernel import ApprovePlan, BlockExecution, MissionState, OpenPlan, apply_event, decide, new_mission


def test_answered_decision_resumes_waiting_activity() -> None:
    activity = new_activity("a-1", "m-1", "execute")
    activity = apply_activity_event(activity, decide_activity(activity, StartActivity())[0])
    activity = apply_activity_event(activity, decide_activity(activity, AwaitHuman("approve"))[0])
    decision = new_decision("d-1", "m-1", "Approve?", "merge")
    decision = apply_decision_event(decision, decide_decision(decision, AnswerDecision("yes"))[0])

    resumed = resume_activity(activity, decision)

    assert resumed.state is ActivityState.RUNNING


def test_answered_decision_resolves_mission_block() -> None:
    mission = new_mission("m-2", "blocked")
    for command in (OpenPlan("hash"), ApprovePlan("hash"), BlockExecution("needs answer")):
        mission = apply_event(mission, decide(mission, command)[0])
    decision = new_decision("d-2", "m-2", "Resolve?", "block")
    decision = apply_decision_event(decision, decide_decision(decision, AnswerDecision("yes"))[0])

    resolved = resolve_block(mission, decision)

    assert resolved.state is MissionState.READY_TO_EXECUTE
