from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from agent_lab.mission.kernel import GateRecord, Mission, MissionState, OracleVerdict


class MissionOperationalStatus(StrEnum):
    """Single composite status for external consumers (dashboards, API clients).

    The write model is intentionally split — MissionState covers the mission's
    life-cycle; execution-level human gates (``Mission.open_gates``) are a
    separate, state-independent side-channel (see
    docs/redesign-2026-07/execution-gate-design-draft-2026-07-13.md). This is
    the single, centrally-owned projection that recombines them into one
    value so consumers don't each reinvent the priority rules. Nothing else
    should compute this independently.
    """

    PLANNING = "PLANNING"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    RUNNING = "RUNNING"
    READY = "READY"
    PAUSED = "PAUSED"  # reserved — no current signal sets this (see design draft)
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_TERMINAL_STATUS: dict[MissionState, MissionOperationalStatus] = {
    MissionState.SUCCEEDED: MissionOperationalStatus.COMPLETED,
    MissionState.FAILED: MissionOperationalStatus.FAILED,
    MissionState.CANCELLED: MissionOperationalStatus.CANCELLED,
}

_STATE_IS_WAITING_FOR_HUMAN = frozenset(
    {
        MissionState.AWAITING_PLAN_DECISION,
        MissionState.AWAITING_DIFF_DECISION,
        MissionState.AWAITING_HUMAN,
    }
)

_RUNNING_STATES = frozenset({MissionState.EXECUTING, MissionState.VERIFYING, MissionState.REPAIRING})


def compute_operational_status(mission: Mission) -> MissionOperationalStatus:
    """Priority order: terminal > waiting-for-human (3 underlying sources) > running > ready > planning.

    Terminal always wins — a completed mission that lost track of closing a
    gate (orphaned gate) still reports COMPLETED; that's a data-hygiene signal
    for the verify query, not something that should un-terminal the status.
    """
    if mission.state in _TERMINAL_STATUS:
        return _TERMINAL_STATUS[mission.state]
    if mission.state in _STATE_IS_WAITING_FOR_HUMAN or mission.open_gates:
        return MissionOperationalStatus.WAITING_FOR_HUMAN
    if mission.state in _RUNNING_STATES:
        return MissionOperationalStatus.RUNNING
    if mission.state is MissionState.READY_TO_EXECUTE:
        return MissionOperationalStatus.READY
    return MissionOperationalStatus.PLANNING  # DRAFTING


@dataclass(frozen=True, slots=True)
class OpenGateSummary:
    gate_id: str
    kind: str


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
    operational_status: MissionOperationalStatus
    open_execution_gates: tuple[OpenGateSummary, ...]
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


def _gate_summary(record: GateRecord) -> OpenGateSummary:
    return OpenGateSummary(gate_id=record.gate_id, kind=record.kind)


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
        operational_status=compute_operational_status(mission),
        open_execution_gates=tuple(_gate_summary(g) for g in mission.open_gates),
        legacy_phase=legacy_phase,
    )
