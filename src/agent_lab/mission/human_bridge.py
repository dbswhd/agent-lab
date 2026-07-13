from __future__ import annotations

from agent_lab.mission.activity import Activity, ActivityState, ResumeActivity, apply_activity_event, decide_activity
from agent_lab.mission.decision_queue import DecisionStatus, HumanDecision
from agent_lab.mission.kernel import Mission, MissionState, ResolveBlock, apply_event, decide


class HumanBridgeError(ValueError):
    pass


def _require_answered(decision: HumanDecision) -> None:
    if decision.status is not DecisionStatus.ANSWERED:
        raise HumanBridgeError("decision must be answered")


def resume_activity(activity: Activity, decision: HumanDecision) -> Activity:
    _require_answered(decision)
    if activity.state not in {ActivityState.WAITING_HUMAN, ActivityState.WAITING_EXTERNAL}:
        raise HumanBridgeError("activity is not waiting")
    return apply_activity_event(activity, decide_activity(activity, ResumeActivity())[0])


def resolve_block(mission: Mission, decision: HumanDecision) -> Mission:
    _require_answered(decision)
    if mission.state is not MissionState.AWAITING_HUMAN:
        raise HumanBridgeError("mission is not waiting for Human")
    return apply_event(mission, decide(mission, ResolveBlock())[0])
