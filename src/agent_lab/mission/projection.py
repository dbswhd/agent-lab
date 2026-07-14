from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict, assert_never

from agent_lab.core.mission_loop import get_mission_loop
from agent_lab.mission.kernel import Mission, MissionState
from agent_lab.mission.read_model import work_phase_from_mission
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.run.state import RunState, RunStateLike

if TYPE_CHECKING:
    # Type-only: keeps `mission` from depending on `runtime` at module-import time
    # (runtime already depends on mission via runtime/snapshot.py — see layer_cycle_check.py).
    from agent_lab.runtime.work_phase import WorkPhase


class MissionLoopAutonomousProjection(TypedDict):
    active: bool


class MissionLoopStatusProjection(TypedDict):
    phase: str
    enabled: bool
    autonomous_segment: MissionLoopAutonomousProjection
    pause_reason: str | None
    circuit_breaker: bool
    circuit_breaker_reason: str | None
    work_phase: WorkPhase
    projection_error_count: int


MISSION_LOOP_STATUS_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "phase",
        "enabled",
        "autonomous_segment",
        "pause_reason",
        "circuit_breaker",
        "circuit_breaker_reason",
        "work_phase",
        "projection_error_count",
    }
)

_COMPATIBILITY_PHASES: Final[frozenset[str]] = frozenset(
    {
        "MISSION_DEFINE",
        "CLARIFY",
        "DISCUSS",
        "PLAN_GATE",
        "PLAN_REJECT",
        "EXECUTE_QUEUE",
        "DRY_RUN",
        "MERGE_REVIEW",
        "VERIFY",
        "REPAIR",
        "MISSION_DONE",
        "MISSION_PAUSED",
    }
)


def _phase_for_mission(mission: Mission, current_phase: str | None) -> str:
    match mission.state:
        case MissionState.DRAFTING:
            if current_phase in {"CLARIFY", "DISCUSS", "PLAN_GATE", "PLAN_REJECT", "MISSION_DEFINE"}:
                return current_phase
            return "DISCUSS"
        case MissionState.AWAITING_PLAN_DECISION:
            return "PLAN_GATE"
        case MissionState.READY_TO_EXECUTE:
            return "EXECUTE_QUEUE"
        case MissionState.EXECUTING:
            return "DRY_RUN"
        case MissionState.AWAITING_DIFF_DECISION:
            return "MERGE_REVIEW"
        case MissionState.VERIFYING:
            return "VERIFY"
        case MissionState.REPAIRING:
            return "REPAIR"
        case MissionState.AWAITING_HUMAN:
            return "MISSION_PAUSED"
        case MissionState.SUCCEEDED | MissionState.FAILED | MissionState.CANCELLED:
            return "MISSION_DONE"
        case unreachable:
            assert_never(unreachable)


def project_mission_loop_status(
    mission: Mission,
    run: RunStateLike,
) -> MissionLoopStatusProjection:
    current = get_mission_loop(run)
    raw_phase = current.get("phase")
    current_phase = raw_phase if isinstance(raw_phase, str) else None
    raw_errors = current.get("projection_error_count")
    error_count = raw_errors if isinstance(raw_errors, int) and raw_errors >= 0 else 0
    if current_phase and current_phase not in _COMPATIBILITY_PHASES:
        error_count += 1

    raw_autonomous = current.get("autonomous_segment")
    autonomous = raw_autonomous if isinstance(raw_autonomous, dict) else {}
    pause_reason = current.get("pause_reason")
    pause_reason = pause_reason if isinstance(pause_reason, str) else None
    circuit_reason = current.get("circuit_breaker_reason")
    circuit_reason = circuit_reason if isinstance(circuit_reason, str) else None
    circuit_breaker = bool(current.get("circuit_breaker"))
    phase = _phase_for_mission(mission, current_phase)
    if phase != "MISSION_DONE" and (circuit_breaker or pause_reason):
        phase = "MISSION_PAUSED"

    return {
        "phase": phase,
        "enabled": bool(current.get("enabled")),
        "autonomous_segment": {"active": bool(autonomous.get("active"))},
        "pause_reason": pause_reason,
        "circuit_breaker": circuit_breaker,
        "circuit_breaker_reason": circuit_reason,
        "work_phase": work_phase_from_mission(mission),
        "projection_error_count": error_count,
    }


def apply_mission_loop_status_projection(folder: Path, mission: Mission) -> None:
    if not (folder / "run.json").is_file():
        return

    current = read_run_meta(folder)
    projection = project_mission_loop_status(mission, current)
    mission_loop = current.get("mission_loop")
    mission_loop = mission_loop if isinstance(mission_loop, dict) else {}
    projected_fields = {key: value for key, value in projection.items() if key != "autonomous_segment"}
    autonomous = mission_loop.get("autonomous_segment")
    autonomous_active = autonomous.get("active") if isinstance(autonomous, dict) else None
    if all(mission_loop.get(key) == value for key, value in projected_fields.items()) and autonomous_active == projection["autonomous_segment"]["active"]:
        return

    def update(run: RunState) -> RunState:
        projection = project_mission_loop_status(mission, run)
        current = run.get("mission_loop")
        mission_loop = dict(current) if isinstance(current, dict) else {}
        projected_fields = {key: value for key, value in projection.items() if key != "autonomous_segment"}
        autonomous = dict(mission_loop.get("autonomous_segment") or {})
        autonomous_active = projection["autonomous_segment"]["active"]
        if all(mission_loop.get(key) == value for key, value in projected_fields.items()) and autonomous.get("active") == autonomous_active:
            return run
        mission_loop.update(projected_fields)
        autonomous["active"] = autonomous_active
        mission_loop["autonomous_segment"] = autonomous
        run["mission_loop"] = mission_loop
        return run

    patch_run_meta(folder, update)
