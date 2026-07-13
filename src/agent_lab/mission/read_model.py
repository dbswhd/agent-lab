from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, assert_never

from agent_lab.mission.kernel import GateRecord, Mission, MissionState, OracleVerdict
from agent_lab.runtime.work_phase import WorkPhase


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
class PlanView:
    phase: str | None
    hash: str | None
    approved_hash: str | None
    pending_approval: bool


@dataclass(frozen=True, slots=True)
class MissionOverviewView:
    phase_label: str
    paused: bool
    circuit_breaker: bool
    pending_inbox_count: int


@dataclass(frozen=True, slots=True)
class InboxSummaryView:
    pending_count: int
    pending_questions: int
    pending_builds: int


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
    plan: PlanView | None = None
    work_phase: WorkPhase | None = None
    mission_overview: MissionOverviewView | None = None
    inbox_summary: InboxSummaryView | None = None
    inbox_items: tuple[dict[str, Any], ...] = ()


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


def work_phase_from_mission(
    mission: Mission,
    *,
    operational_status: MissionOperationalStatus | None = None,
) -> WorkPhase:
    """Map Mission operational status + state → Work tab stepper phase (Wave A)."""
    status = operational_status if operational_status is not None else compute_operational_status(mission)
    if status is MissionOperationalStatus.COMPLETED:
        return "done"
    if status in {MissionOperationalStatus.FAILED, MissionOperationalStatus.CANCELLED}:
        return "done"
    if status is MissionOperationalStatus.WAITING_FOR_HUMAN:
        if mission.state is MissionState.AWAITING_DIFF_DECISION:
            return "review_needed"
        if mission.state in {MissionState.EXECUTING, MissionState.VERIFYING, MissionState.REPAIRING} and mission.open_gates:
            return "review_needed"
        if mission.state is MissionState.AWAITING_PLAN_DECISION:
            return "plan_draft"
        return "review_needed"
    if status is MissionOperationalStatus.RUNNING:
        if mission.state in {MissionState.VERIFYING, MissionState.REPAIRING}:
            return "merge_verify"
        return "execute_pending"
    if status is MissionOperationalStatus.READY:
        return "execute_pending"
    return "plan_draft"


def plan_phase_from_mission(mission: Mission, *, legacy_plan_phase: str | None = None) -> str:
    """Prefer Mission readiness; fall back to legacy plan_workflow.phase when drafting."""
    if mission.state is MissionState.AWAITING_PLAN_DECISION:
        return "HUMAN_PENDING"
    if mission.approved_plan_hash and mission.state in {
        MissionState.READY_TO_EXECUTE,
        MissionState.EXECUTING,
        MissionState.AWAITING_DIFF_DECISION,
        MissionState.VERIFYING,
        MissionState.REPAIRING,
        MissionState.AWAITING_HUMAN,
        MissionState.SUCCEEDED,
        MissionState.FAILED,
        MissionState.CANCELLED,
    }:
        return "APPROVED"
    if legacy_plan_phase and str(legacy_plan_phase).strip():
        return str(legacy_plan_phase).strip().upper()
    if mission.state is MissionState.DRAFTING:
        return "CLARIFY"
    return "INTAKE"


def _inbox_summary_from_run(run: dict[str, Any], *, open_gate_count: int = 0) -> InboxSummaryView:
    from agent_lab.human_inbox import public_inbox_payload

    payload = public_inbox_payload(run)
    pending_count = max(int(payload.get("pending_count") or 0), open_gate_count)
    return InboxSummaryView(
        pending_count=pending_count,
        pending_questions=int(payload.get("pending_questions") or 0),
        pending_builds=int(payload.get("pending_builds") or 0),
    )


def _plan_view_from_run_and_mission(
    mission: Mission | None,
    run: dict[str, Any],
) -> PlanView:
    pw = run.get("plan_workflow") if isinstance(run.get("plan_workflow"), dict) else {}
    legacy_phase = str(pw.get("phase") or "").strip().upper() or None
    if mission is None:
        phase = legacy_phase
        plan_hash = str(pw.get("plan_hash_at_approval") or "") or None
        return PlanView(
            phase=phase,
            hash=plan_hash,
            approved_hash=plan_hash if phase == "APPROVED" else None,
            pending_approval=phase == "HUMAN_PENDING",
        )
    phase = plan_phase_from_mission(mission, legacy_plan_phase=legacy_phase)
    return PlanView(
        phase=phase,
        hash=mission.current_plan_hash or str(pw.get("plan_hash_at_approval") or "") or None,
        approved_hash=mission.approved_plan_hash or (
            str(pw.get("plan_hash_at_approval") or "") or None if phase == "APPROVED" else None
        ),
        pending_approval=phase == "HUMAN_PENDING",
    )


def _overview_from_mission(
    mission: Mission,
    *,
    operational_status: MissionOperationalStatus,
    pending_inbox_count: int,
    legacy_phase: str | None,
    circuit_breaker: bool = False,
) -> MissionOverviewView:
    phase_label = legacy_phase or operational_status.value
    paused = False  # PAUSED reserved; circuit_breaker may imply pause in legacy UI
    return MissionOverviewView(
        phase_label=str(phase_label),
        paused=paused,
        circuit_breaker=circuit_breaker,
        pending_inbox_count=pending_inbox_count,
    )


def build_read_model(
    mission: Mission,
    *,
    legacy_phase: str | None = None,
    run: dict[str, Any] | None = None,
) -> MissionReadModel:
    run_meta = run if isinstance(run, dict) else {}
    operational = compute_operational_status(mission)
    inbox = _inbox_summary_from_run(run_meta, open_gate_count=len(mission.open_gates))
    ml = run_meta.get("mission_loop") if isinstance(run_meta.get("mission_loop"), dict) else {}
    circuit = bool(ml.get("circuit_breaker"))
    plan = _plan_view_from_run_and_mission(mission, run_meta)
    overview = _overview_from_mission(
        mission,
        operational_status=operational,
        pending_inbox_count=inbox.pending_count,
        legacy_phase=legacy_phase,
        circuit_breaker=circuit,
    )
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
        operational_status=operational,
        open_execution_gates=tuple(_gate_summary(g) for g in mission.open_gates),
        legacy_phase=legacy_phase,
        plan=plan,
        work_phase=work_phase_from_mission(mission, operational_status=operational),
        mission_overview=overview,
        inbox_summary=inbox,
        inbox_items=(),
    )


def build_legacy_composites(run: dict[str, Any]) -> dict[str, Any]:
    """Wave A composites for unmigrated sessions (run.json only)."""
    plan = _plan_view_from_run_and_mission(None, run)
    inbox = _inbox_summary_from_run(run, open_gate_count=0)
    ml = run.get("mission_loop") if isinstance(run.get("mission_loop"), dict) else {}
    legacy_phase = ml.get("phase") if isinstance(ml.get("phase"), str) else None
    overview = MissionOverviewView(
        phase_label=str(legacy_phase or plan.phase or "LEGACY"),
        paused=bool(ml.get("pause_reason") or ml.get("circuit_breaker")),
        circuit_breaker=bool(ml.get("circuit_breaker")),
        pending_inbox_count=inbox.pending_count,
    )
    work: WorkPhase | None = None
    if legacy_phase:
        from agent_lab.runtime.work_phase import resolve_work_phase_from_mission

        work = resolve_work_phase_from_mission(legacy_phase)
    if work is None and plan.phase == "APPROVED":
        work = "execute_pending"
    if work is None:
        work = "plan_draft"
    return {
        "plan": {
            "phase": plan.phase,
            "hash": plan.hash,
            "approved_hash": plan.approved_hash,
            "pending_approval": plan.pending_approval,
        },
        "work_phase": work,
        "mission_overview": {
            "phase_label": overview.phase_label,
            "paused": overview.paused,
            "circuit_breaker": overview.circuit_breaker,
            "pending_inbox_count": overview.pending_inbox_count,
        },
        "inbox_summary": {
            "pending_count": inbox.pending_count,
            "pending_questions": inbox.pending_questions,
            "pending_builds": inbox.pending_builds,
        },
        "inbox_items": [],
    }


def session_run_for_read_model(folder: Path) -> dict[str, Any]:
    from agent_lab.run.meta import read_run_meta

    return read_run_meta(folder)
