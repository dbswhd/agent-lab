from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from agent_lab.mission.kernel import Mission, MissionState, OracleVerdict


@dataclass(frozen=True, slots=True)
class MissionReadModel:
    mission_id: str
    goal: str
    state: MissionState
    version: int
    plan_revision: int
    plan_hash: str | None
    approved_plan_hash: str | None
    repair_attempt: int
    max_repair_attempts: int
    oracle_verdict: OracleVerdict | None
    next_action: str
    event_cursor: int
    legacy_phase: str | None = None


def _next_action(state: MissionState) -> str:
    match state:
        case MissionState.DRAFTING:
            return "draft_plan"
        case MissionState.AWAITING_PLAN_DECISION:
            return "decide_plan"
        case MissionState.READY_TO_EXECUTE:
            return "start_execution"
        case MissionState.EXECUTING:
            return "observe_execution"
        case MissionState.AWAITING_DIFF_DECISION:
            return "decide_diff"
        case MissionState.VERIFYING:
            return "observe_verification"
        case MissionState.REPAIRING:
            return "observe_repair"
        case MissionState.AWAITING_HUMAN:
            return "answer_human"
        case MissionState.SUCCEEDED:
            return "view_result"
        case MissionState.FAILED:
            return "inspect_failure"
        case MissionState.CANCELLED:
            return "close_or_restart"
        case _ as unreachable:
            assert_never(unreachable)


def build_read_model(mission: Mission, *, legacy_phase: str | None = None) -> MissionReadModel:
    return MissionReadModel(
        mission_id=str(mission.id),
        goal=mission.goal,
        state=mission.state,
        version=mission.version,
        plan_revision=mission.plan_revision,
        plan_hash=mission.current_plan_hash,
        approved_plan_hash=mission.approved_plan_hash,
        repair_attempt=mission.repair_attempt,
        max_repair_attempts=mission.max_repair_attempts,
        oracle_verdict=mission.last_oracle_verdict,
        next_action=_next_action(mission.state),
        event_cursor=mission.version,
        legacy_phase=legacy_phase,
    )
