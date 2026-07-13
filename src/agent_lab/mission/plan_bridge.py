from __future__ import annotations

from dataclasses import dataclass

from agent_lab.mission.kernel import (
    ApprovePlan,
    Mission,
    MissionCommand,
    MissionEvent,
    MissionState,
    OpenPlan,
    RejectPlan,
    apply_event,
    decide,
)
from agent_lab.plan.pending import plan_content_hash


@dataclass(frozen=True, slots=True)
class PlanApprovalDecision:
    approved: bool
    note: str = ""


def _apply_batch(mission: Mission, events: tuple[MissionEvent, ...]) -> Mission:
    current = mission
    for event in events:
        current = apply_event(current, event)
    return current


def _decision_command(decision: PlanApprovalDecision, plan_hash: str) -> MissionCommand:
    if decision.approved:
        return ApprovePlan(plan_hash)
    return RejectPlan(decision.note)


def plan_decision_events(
    mission: Mission,
    plan_md: str,
    decision: PlanApprovalDecision,
) -> tuple[MissionEvent, ...]:
    plan_hash = plan_content_hash(plan_md)
    events: list[MissionEvent] = []
    current = mission
    pending_same_revision = current.state is MissionState.AWAITING_PLAN_DECISION and current.current_plan_hash == plan_hash
    if not pending_same_revision:
        opened = decide(current, OpenPlan(plan_hash))
        events.extend(opened)
        current = _apply_batch(current, opened)
    final = decide(current, _decision_command(decision, plan_hash))
    events.extend(final)
    return tuple(events)
