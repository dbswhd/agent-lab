from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import assert_never


class ActivityState(StrEnum):
    SCHEDULED = "SCHEDULED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    WAITING_HUMAN = "WAITING_HUMAN"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class ActivityTransitionError(Exception):
    def __init__(self, command: str, state: ActivityState, reason: str) -> None:
        self.command = command
        self.state = state
        self.reason = reason
        super().__init__(command, state, reason)

    def __str__(self) -> str:
        return f"{self.command} rejected in {self.state}: {self.reason}"


@dataclass(frozen=True, slots=True)
class Activity:
    id: str
    mission_id: str
    kind: str
    state: ActivityState = ActivityState.SCHEDULED
    attempt: int = 0
    max_attempts: int = 2
    wait_reason: str | None = None
    failure_reason: str | None = None
    lease_owner: str | None = None
    lease_token: str | None = None
    lease_expires_at: float | None = None


@dataclass(frozen=True, slots=True)
class ClaimActivity:
    owner_id: str
    lease_token: str
    lease_expires_at: float


@dataclass(frozen=True, slots=True)
class HeartbeatActivity:
    lease_expires_at: float


@dataclass(frozen=True, slots=True)
class ReleaseClaim:
    pass


@dataclass(frozen=True, slots=True)
class StartActivity:
    pass


@dataclass(frozen=True, slots=True)
class AwaitExternal:
    reason: str


@dataclass(frozen=True, slots=True)
class AwaitHuman:
    reason: str


@dataclass(frozen=True, slots=True)
class ResumeActivity:
    pass


@dataclass(frozen=True, slots=True)
class CompleteActivity:
    pass


@dataclass(frozen=True, slots=True)
class FailActivity:
    reason: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class CancelActivity:
    pass


@dataclass(frozen=True, slots=True)
class TimeoutActivity:
    pass


ActivityCommand = (
    ClaimActivity
    | HeartbeatActivity
    | ReleaseClaim
    | StartActivity
    | AwaitExternal
    | AwaitHuman
    | ResumeActivity
    | CompleteActivity
    | FailActivity
    | CancelActivity
    | TimeoutActivity
)


@dataclass(frozen=True, slots=True)
class ActivityStarted:
    pass


@dataclass(frozen=True, slots=True)
class ActivityClaimed:
    owner_id: str
    lease_token: str
    lease_expires_at: float


@dataclass(frozen=True, slots=True)
class ActivityHeartbeat:
    lease_expires_at: float


@dataclass(frozen=True, slots=True)
class ClaimReleased:
    pass


@dataclass(frozen=True, slots=True)
class ActivityWaitingExternal:
    reason: str


@dataclass(frozen=True, slots=True)
class ActivityWaitingHuman:
    reason: str


@dataclass(frozen=True, slots=True)
class ActivityResumed:
    pass


@dataclass(frozen=True, slots=True)
class ActivityCompleted:
    pass


@dataclass(frozen=True, slots=True)
class ActivityFailed:
    reason: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class ActivityCancelled:
    pass


@dataclass(frozen=True, slots=True)
class ActivityTimedOut:
    pass


ActivityEvent = (
    ActivityClaimed
    | ActivityHeartbeat
    | ClaimReleased
    | ActivityStarted
    | ActivityWaitingExternal
    | ActivityWaitingHuman
    | ActivityResumed
    | ActivityCompleted
    | ActivityFailed
    | ActivityCancelled
    | ActivityTimedOut
)


def new_activity(activity_id: str, mission_id: str, kind: str, *, max_attempts: int = 2) -> Activity:
    return Activity(activity_id, mission_id, kind, max_attempts=max(1, max_attempts))


def _reject(activity: Activity, command: ActivityCommand, reason: str) -> ActivityTransitionError:
    return ActivityTransitionError(type(command).__name__, activity.state, reason)


def _require(activity: Activity, command: ActivityCommand, *states: ActivityState) -> None:
    if activity.state not in states:
        expected = ", ".join(state.value for state in states)
        raise _reject(activity, command, f"expected {expected}")


def decide_activity(activity: Activity, command: ActivityCommand) -> tuple[ActivityEvent, ...]:
    match command:
        case ClaimActivity(owner_id=owner_id, lease_token=lease_token, lease_expires_at=lease_expires_at):
            _require(activity, command, ActivityState.SCHEDULED, ActivityState.FAILED_RETRYABLE)
            if not owner_id or not lease_token or lease_expires_at <= 0:
                raise _reject(activity, command, "lease identity and expiry are required")
            return (ActivityClaimed(owner_id, lease_token, lease_expires_at),)
        case HeartbeatActivity(lease_expires_at=lease_expires_at):
            _require(activity, command, ActivityState.CLAIMED, ActivityState.RUNNING)
            if lease_expires_at <= 0:
                raise _reject(activity, command, "lease expiry is required")
            return (ActivityHeartbeat(lease_expires_at),)
        case ReleaseClaim():
            _require(activity, command, ActivityState.CLAIMED)
            return (ClaimReleased(),)
        case StartActivity():
            _require(activity, command, ActivityState.SCHEDULED, ActivityState.CLAIMED, ActivityState.FAILED_RETRYABLE)
            return (ActivityStarted(),)
        case AwaitExternal(reason=reason):
            _require(activity, command, ActivityState.RUNNING)
            return (ActivityWaitingExternal(reason),)
        case AwaitHuman(reason=reason):
            _require(activity, command, ActivityState.RUNNING)
            return (ActivityWaitingHuman(reason),)
        case ResumeActivity():
            _require(activity, command, ActivityState.WAITING_HUMAN, ActivityState.WAITING_EXTERNAL)
            return (ActivityResumed(),)
        case CompleteActivity():
            _require(activity, command, ActivityState.RUNNING, ActivityState.WAITING_EXTERNAL)
            return (ActivityCompleted(),)
        case FailActivity(reason=reason, retryable=retryable):
            _require(activity, command, ActivityState.RUNNING, ActivityState.WAITING_EXTERNAL)
            return (ActivityFailed(reason, retryable and activity.attempt < activity.max_attempts),)
        case CancelActivity():
            _require(
                activity,
                command,
                ActivityState.SCHEDULED,
                ActivityState.CLAIMED,
                ActivityState.RUNNING,
                ActivityState.WAITING_EXTERNAL,
                ActivityState.WAITING_HUMAN,
                ActivityState.FAILED_RETRYABLE,
            )
            return (ActivityCancelled(),)
        case TimeoutActivity():
            _require(activity, command, ActivityState.RUNNING, ActivityState.WAITING_EXTERNAL)
            return (ActivityTimedOut(),)
        case _ as unreachable:
            assert_never(unreachable)


def apply_activity_event(activity: Activity, event: ActivityEvent) -> Activity:
    match event:
        case ActivityClaimed(owner_id=owner_id, lease_token=lease_token, lease_expires_at=lease_expires_at):
            return replace(
                activity,
                state=ActivityState.CLAIMED,
                lease_owner=owner_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
            )
        case ActivityHeartbeat(lease_expires_at=lease_expires_at):
            return replace(activity, lease_expires_at=lease_expires_at)
        case ClaimReleased():
            return replace(activity, state=ActivityState.SCHEDULED, lease_owner=None, lease_token=None, lease_expires_at=None)
        case ActivityStarted():
            return replace(activity, state=ActivityState.RUNNING, wait_reason=None, failure_reason=None)
        case ActivityWaitingExternal(reason=reason):
            return replace(activity, state=ActivityState.WAITING_EXTERNAL, wait_reason=reason)
        case ActivityWaitingHuman(reason=reason):
            return replace(activity, state=ActivityState.WAITING_HUMAN, wait_reason=reason)
        case ActivityResumed():
            return replace(activity, state=ActivityState.RUNNING, wait_reason=None)
        case ActivityCompleted():
            return replace(activity, state=ActivityState.SUCCEEDED, wait_reason=None, lease_owner=None, lease_token=None, lease_expires_at=None)
        case ActivityFailed(reason=reason, retryable=retryable):
            next_attempt = activity.attempt + 1
            state = ActivityState.FAILED_RETRYABLE if retryable else ActivityState.FAILED_TERMINAL
            return replace(
                activity,
                state=state,
                attempt=next_attempt,
                failure_reason=reason,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
            )
        case ActivityCancelled():
            return replace(activity, state=ActivityState.CANCELLED, lease_owner=None, lease_token=None, lease_expires_at=None)
        case ActivityTimedOut():
            return replace(activity, state=ActivityState.TIMED_OUT, lease_owner=None, lease_token=None, lease_expires_at=None)
        case _ as unreachable:
            assert_never(unreachable)
