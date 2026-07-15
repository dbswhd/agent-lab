from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

from agent_lab.mission.lease import ActivityLeaseStore, LeaseConflictError
from agent_lab.mission.recovery import RecoveryAction, SideEffectState, decide_recovery


def _claim_from_process(path_text: str, owner_id: str, queue: multiprocessing.Queue[str]) -> None:
    try:
        ActivityLeaseStore(Path(path_text)).claim(
            "activity-1",
            "mission-1",
            owner_id,
            now=10.0,
            ttl_s=30.0,
        )
    except LeaseConflictError:
        queue.put("conflict")
    else:
        queue.put("ok")


def test_lease_claim_heartbeat_release_survives_store_restart(tmp_path: Path) -> None:
    path = tmp_path / "leases.json"
    store = ActivityLeaseStore(path)
    lease = store.claim("activity-1", "mission-1", "worker-a", now=10.0, ttl_s=5.0)

    renewed = ActivityLeaseStore(path).heartbeat(
        "activity-1", "worker-a", lease.token, now=12.0, ttl_s=5.0
    )
    assert renewed.expires_at == 17.0
    ActivityLeaseStore(path).release("activity-1", "worker-a", lease.token, now=13.0)
    assert ActivityLeaseStore(path).snapshot() == ()


def test_lease_rejects_live_owner_and_allows_expired_reclaim(tmp_path: Path) -> None:
    store = ActivityLeaseStore(tmp_path / "leases.json")
    store.claim("activity-1", "mission-1", "worker-a", now=10.0, ttl_s=5.0)

    with pytest.raises(LeaseConflictError):
        store.claim("activity-1", "mission-1", "worker-b", now=12.0, ttl_s=5.0)

    expired = store.recover_expired(now=15.0)
    assert [lease.activity_id for lease in expired] == ["activity-1"]
    reclaimed = store.claim("activity-1", "mission-1", "worker-b", now=16.0, ttl_s=5.0)
    assert reclaimed.owner_id == "worker-b"


def test_lease_serializes_cross_process_claim(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    path = tmp_path / "leases.json"
    processes = [
        context.Process(target=_claim_from_process, args=(str(path), owner_id, queue))
        for owner_id in ("worker-a", "worker-b")
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)

    assert all(process.exitcode == 0 for process in processes)
    assert sorted(queue.get(timeout=2) for _ in processes) == ["conflict", "ok"]


@pytest.mark.parametrize(
    ("state", "action"),
    (
        (SideEffectState.NOT_STARTED, RecoveryAction.REQUEUE),
        (SideEffectState.STARTED, RecoveryAction.RECONCILE),
        (SideEffectState.COMMITTED, RecoveryAction.COMPLETE),
        (SideEffectState.FAILED, RecoveryAction.RETRY),
    ),
)
def test_side_effect_recovery_never_retries_ambiguous_started_work(
    state: SideEffectState, action: RecoveryAction
) -> None:
    assert decide_recovery("activity-1", state).action is action
