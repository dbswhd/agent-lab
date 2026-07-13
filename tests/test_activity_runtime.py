from __future__ import annotations

import pytest

from agent_lab.mission.activity import (
    Activity,
    ActivityState,
    ActivityTransitionError,
    AwaitHuman,
    ClaimActivity,
    CompleteActivity,
    FailActivity,
    HeartbeatActivity,
    ReleaseClaim,
    StartActivity,
    apply_activity_event,
    decide_activity,
    new_activity,
)


def test_activity_runs_and_completes_without_client_connection() -> None:
    activity = new_activity("a-1", "m-1", "agent_execute")
    for command in (StartActivity(), CompleteActivity()):
        activity = apply_activity_event(activity, decide_activity(activity, command)[0])
    assert activity.state is ActivityState.SUCCEEDED


def test_human_wait_releases_running_activity() -> None:
    activity = new_activity("a-1", "m-1", "human_decision")
    activity = apply_activity_event(activity, decide_activity(activity, StartActivity())[0])
    activity = apply_activity_event(activity, decide_activity(activity, AwaitHuman("approve diff"))[0])
    assert activity.state is ActivityState.WAITING_HUMAN
    with pytest.raises(ActivityTransitionError):
        decide_activity(activity, StartActivity())


def test_retryable_failure_has_bounded_attempts() -> None:
    activity = new_activity("a-1", "m-1", "oracle", max_attempts=1)
    activity = apply_activity_event(activity, decide_activity(activity, StartActivity())[0])
    activity = apply_activity_event(activity, decide_activity(activity, FailActivity("tests red", retryable=True))[0])
    assert activity.state is ActivityState.FAILED_RETRYABLE
    activity = apply_activity_event(activity, decide_activity(activity, StartActivity())[0])
    activity = apply_activity_event(activity, decide_activity(activity, FailActivity("tests red", retryable=True))[0])
    assert activity.state is ActivityState.FAILED_TERMINAL


def test_activity_is_immutable_after_event_application() -> None:
    activity = new_activity("a-1", "m-1", "agent_execute")
    next_activity = apply_activity_event(activity, decide_activity(activity, StartActivity())[0])
    assert isinstance(activity, Activity)
    assert activity.state is ActivityState.SCHEDULED
    assert next_activity.state is ActivityState.RUNNING


def test_activity_claim_heartbeat_and_release_are_explicit() -> None:
    activity = new_activity("a-1", "m-1", "agent_execute")
    activity = apply_activity_event(
        activity,
        decide_activity(activity, ClaimActivity("worker-a", "token-a", 15.0))[0],
    )
    assert activity.state is ActivityState.CLAIMED
    assert activity.lease_owner == "worker-a"

    activity = apply_activity_event(activity, decide_activity(activity, HeartbeatActivity(20.0))[0])
    assert activity.lease_expires_at == 20.0
    activity = apply_activity_event(activity, decide_activity(activity, ReleaseClaim())[0])
    assert activity.state is ActivityState.SCHEDULED
    assert activity.lease_owner is None
