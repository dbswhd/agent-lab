from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import NewType, assert_never

from agent_lab.mission.errors import MissionTransitionError

MissionId = NewType("MissionId", str)


class MissionState(StrEnum):
    DRAFTING = "DRAFTING"
    AWAITING_PLAN_DECISION = "AWAITING_PLAN_DECISION"
    READY_TO_EXECUTE = "READY_TO_EXECUTE"
    EXECUTING = "EXECUTING"
    AWAITING_DIFF_DECISION = "AWAITING_DIFF_DECISION"
    VERIFYING = "VERIFYING"
    REPAIRING = "REPAIRING"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OracleVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class Mission:
    id: MissionId
    goal: str
    state: MissionState = MissionState.DRAFTING
    version: int = 0
    plan_revision: int = 0
    current_plan_hash: str | None = None
    approved_plan_hash: str | None = None
    repair_attempt: int = 0
    max_repair_attempts: int = 2
    blocked: bool = False
    last_oracle_verdict: OracleVerdict | None = None
    last_oracle_detail: str | None = None
    merged_commit_sha: str | None = None


@dataclass(frozen=True, slots=True)
class OpenPlan:
    plan_hash: str


@dataclass(frozen=True, slots=True)
class RejectPlan:
    reason: str


@dataclass(frozen=True, slots=True)
class ApprovePlan:
    plan_hash: str


@dataclass(frozen=True, slots=True)
class StartExecution:
    pass


@dataclass(frozen=True, slots=True)
class MarkDiffReady:
    pass


@dataclass(frozen=True, slots=True)
class ApproveDiff:
    pass


@dataclass(frozen=True, slots=True)
class RecordMerge:
    commit_sha: str


@dataclass(frozen=True, slots=True)
class RecordOracle:
    verdict: OracleVerdict
    detail: str = ""


@dataclass(frozen=True, slots=True)
class BlockExecution:
    reason: str


@dataclass(frozen=True, slots=True)
class ResolveBlock:
    pass


MissionCommand = OpenPlan | RejectPlan | ApprovePlan | StartExecution | MarkDiffReady | ApproveDiff | RecordMerge | RecordOracle | BlockExecution | ResolveBlock


@dataclass(frozen=True, slots=True)
class PlanOpened:
    plan_hash: str
    revision: int


@dataclass(frozen=True, slots=True)
class PlanRejected:
    reason: str


@dataclass(frozen=True, slots=True)
class PlanApproved:
    plan_hash: str


@dataclass(frozen=True, slots=True)
class ExecutionStarted:
    pass


@dataclass(frozen=True, slots=True)
class DiffReady:
    pass


@dataclass(frozen=True, slots=True)
class DiffApproved:
    pass


@dataclass(frozen=True, slots=True)
class MergeCommitted:
    commit_sha: str


@dataclass(frozen=True, slots=True)
class OraclePassed:
    detail: str


@dataclass(frozen=True, slots=True)
class OracleFailed:
    detail: str
    terminal: bool


@dataclass(frozen=True, slots=True)
class RepairScheduled:
    attempt: int
    detail: str = ""


@dataclass(frozen=True, slots=True)
class BlockOpened:
    reason: str


@dataclass(frozen=True, slots=True)
class BlockResolved:
    pass


MissionEvent = (
    PlanOpened
    | PlanRejected
    | PlanApproved
    | ExecutionStarted
    | DiffReady
    | DiffApproved
    | MergeCommitted
    | OraclePassed
    | OracleFailed
    | RepairScheduled
    | BlockOpened
    | BlockResolved
)


def new_mission(mission_id: str, goal: str) -> Mission:
    return Mission(id=MissionId(mission_id), goal=goal)


def _reject(mission: Mission, command: MissionCommand, reason: str) -> MissionTransitionError:
    return MissionTransitionError(type(command).__name__, mission.state, reason)


def _require_state(mission: Mission, command: MissionCommand, *allowed: MissionState) -> None:
    if mission.state not in allowed:
        expected = ", ".join(state.value for state in allowed)
        raise _reject(mission, command, f"expected {expected}")


def decide(mission: Mission, command: MissionCommand, *, expected_version: int | None = None) -> tuple[MissionEvent, ...]:
    if expected_version is not None and mission.version != expected_version:
        raise _reject(mission, command, f"expected version {expected_version}, got {mission.version}")
    match command:
        case OpenPlan(plan_hash=plan_hash):
            _require_state(
                mission,
                command,
                MissionState.DRAFTING,
                MissionState.AWAITING_PLAN_DECISION,
                MissionState.READY_TO_EXECUTE,
            )
            if not plan_hash:
                raise _reject(mission, command, "plan hash is required")
            return (PlanOpened(plan_hash, mission.plan_revision + 1),)
        case RejectPlan(reason=reason):
            _require_state(mission, command, MissionState.AWAITING_PLAN_DECISION)
            return (PlanRejected(reason),)
        case ApprovePlan(plan_hash=plan_hash):
            _require_state(mission, command, MissionState.AWAITING_PLAN_DECISION)
            if plan_hash != mission.current_plan_hash:
                raise _reject(mission, command, "plan hash does not match current revision")
            return (PlanApproved(plan_hash),)
        case StartExecution():
            _require_state(mission, command, MissionState.READY_TO_EXECUTE)
            if mission.blocked:
                raise _reject(mission, command, "execution is blocked")
            return (ExecutionStarted(),)
        case MarkDiffReady():
            _require_state(mission, command, MissionState.EXECUTING, MissionState.REPAIRING)
            return (DiffReady(),)
        case ApproveDiff():
            _require_state(mission, command, MissionState.AWAITING_DIFF_DECISION)
            return (DiffApproved(),)
        case RecordMerge(commit_sha=commit_sha):
            _require_state(mission, command, MissionState.VERIFYING)
            if not commit_sha:
                raise _reject(mission, command, "commit sha is required")
            return (MergeCommitted(commit_sha),)
        case RecordOracle(verdict=verdict, detail=detail):
            _require_state(mission, command, MissionState.VERIFYING)
            if mission.merged_commit_sha is None:
                raise _reject(mission, command, "merge must be recorded before Oracle")
            if verdict is OracleVerdict.PASS:
                return (OraclePassed(detail),)
            next_attempt = mission.repair_attempt + 1
            terminal = next_attempt > mission.max_repair_attempts
            if terminal:
                return (OracleFailed(detail, terminal),)
            return (RepairScheduled(next_attempt, detail),)
        case BlockExecution(reason=reason):
            _require_state(mission, command, MissionState.READY_TO_EXECUTE)
            return (BlockOpened(reason),)
        case ResolveBlock():
            _require_state(mission, command, MissionState.AWAITING_HUMAN)
            if not mission.blocked:
                raise _reject(mission, command, "no active execution block")
            return (BlockResolved(),)
        case _ as unreachable:
            assert_never(unreachable)


def apply_event(mission: Mission, event: MissionEvent) -> Mission:
    next_version = mission.version + 1
    match event:
        case PlanOpened(plan_hash=plan_hash, revision=revision):
            return replace(
                mission,
                version=next_version,
                state=MissionState.AWAITING_PLAN_DECISION,
                plan_revision=revision,
                current_plan_hash=plan_hash,
                approved_plan_hash=None,
                blocked=False,
                merged_commit_sha=None,
            )
        case PlanRejected():
            return replace(mission, version=next_version, state=MissionState.DRAFTING, approved_plan_hash=None)
        case PlanApproved(plan_hash=plan_hash):
            return replace(mission, version=next_version, state=MissionState.READY_TO_EXECUTE, approved_plan_hash=plan_hash)
        case ExecutionStarted():
            return replace(mission, version=next_version, state=MissionState.EXECUTING)
        case DiffReady():
            return replace(mission, version=next_version, state=MissionState.AWAITING_DIFF_DECISION)
        case DiffApproved():
            return replace(mission, version=next_version, state=MissionState.VERIFYING)
        case MergeCommitted(commit_sha=commit_sha):
            return replace(mission, version=next_version, merged_commit_sha=commit_sha)
        case OraclePassed(detail=detail):
            return replace(
                mission,
                version=next_version,
                state=MissionState.SUCCEEDED,
                last_oracle_verdict=OracleVerdict.PASS,
                last_oracle_detail=detail,
            )
        case OracleFailed(detail=detail, terminal=terminal):
            return replace(
                mission,
                version=next_version,
                state=MissionState.FAILED if terminal else MissionState.VERIFYING,
                last_oracle_verdict=OracleVerdict.FAIL,
                last_oracle_detail=detail,
            )
        case RepairScheduled(attempt=attempt, detail=detail):
            return replace(
                mission,
                version=next_version,
                state=MissionState.REPAIRING,
                repair_attempt=attempt,
                last_oracle_verdict=OracleVerdict.FAIL,
                last_oracle_detail=detail,
                merged_commit_sha=None,
            )
        case BlockOpened():
            return replace(mission, version=next_version, state=MissionState.AWAITING_HUMAN, blocked=True)
        case BlockResolved():
            return replace(mission, version=next_version, state=MissionState.READY_TO_EXECUTE, blocked=False)
        case _ as unreachable:
            assert_never(unreachable)
