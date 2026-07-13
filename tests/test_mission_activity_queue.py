from __future__ import annotations

from pathlib import Path

from agent_lab.mission.activity_queue import ActivityQueue, QueueState, QueuedActivity
from agent_lab.mission.recovery import RecoveryAction, SideEffectState


def _activity(activity_id: str, priority: int = 1) -> QueuedActivity:
    return QueuedActivity(activity_id, "mission-1", "execute", priority, f"key-{activity_id}")


def test_queue_is_idempotent_and_claims_highest_priority(tmp_path: Path) -> None:
    queue = ActivityQueue.for_session(tmp_path)
    queue.enqueue(_activity("low", priority=1))
    queue.enqueue(_activity("high", priority=5))

    assert queue.enqueue(_activity("high", priority=5)).activity_id == "high"
    claimed = queue.claim_next("worker-a", now=10.0, ttl_s=5.0)

    assert claimed is not None
    assert claimed.activity.activity_id == "high"
    assert claimed.activity.state is QueueState.CLAIMED


def test_queue_requeues_unstarted_expired_claim(tmp_path: Path) -> None:
    queue = ActivityQueue.for_session(tmp_path)
    queue.enqueue(_activity("a-1"))
    claimed = queue.claim_next("worker-a", now=10.0, ttl_s=5.0)
    assert claimed is not None

    decisions = queue.recover(now=15.0)

    assert decisions[0].action is RecoveryAction.REQUEUE
    assert queue.snapshot()[0].state is QueueState.QUEUED
    assert queue.leases.snapshot() == ()


def test_queue_never_retries_ambiguous_side_effect(tmp_path: Path) -> None:
    queue = ActivityQueue.for_session(tmp_path)
    queue.enqueue(_activity("a-1"))
    claimed = queue.claim_next("worker-a", now=10.0, ttl_s=5.0)
    assert claimed is not None
    queue.record_side_effect("a-1", "worker-a", claimed.lease.token, SideEffectState.STARTED)

    decisions = queue.recover(now=15.0)

    assert decisions[0].action is RecoveryAction.RECONCILE
    assert queue.snapshot()[0].state is QueueState.NEEDS_RECONCILE
    assert queue.leases.snapshot() == ()


def test_queue_complete_is_durable_and_releases_lease(tmp_path: Path) -> None:
    queue = ActivityQueue.for_session(tmp_path)
    queue.enqueue(_activity("a-1"))
    claimed = queue.claim_next("worker-a", now=10.0, ttl_s=5.0)
    assert claimed is not None

    completed = queue.complete("a-1", "worker-a", claimed.lease.token, now=11.0)

    assert completed.state is QueueState.COMPLETED
    assert ActivityQueue.for_session(tmp_path).snapshot()[0].state is QueueState.COMPLETED
    assert ActivityQueue.for_session(tmp_path).leases.snapshot() == ()
