"""ActivityQueue crash-recovery orchestration: startup eager scan + throttled tick safety-net."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.mission.activity_queue import ActivityQueue, QueueState, QueuedActivity
from agent_lab.mission.activity_recovery import (
    _flock,
    _lock_path,
    activity_queue_recovery_enabled,
    recover_activity_queue,
    recovery_due,
)
from agent_lab.mission.recovery import SideEffectState


def _seed_committed_activity(sessions_root: Path, name: str) -> Path:
    folder = sessions_root / name
    folder.mkdir(parents=True)
    queue = ActivityQueue.for_session(folder)
    activity = QueuedActivity(f"activity-{name}", name, "execute", 1, "key-1")
    queue.enqueue(activity)
    claimed = queue.claim_next("worker-a", now=10.0, ttl_s=5.0)
    assert claimed is not None
    queue.record_side_effect(activity.activity_id, "worker-a", claimed.lease.token, SideEffectState.COMMITTED)
    return folder


def test_recover_activity_queue_completes_committed_side_effect(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    folder = _seed_committed_activity(sessions_root, "sess-1")

    summary = recover_activity_queue(sessions_root, reason="test", now=100.0, blocking=True)

    assert summary["enabled"] is True
    assert summary["locked_out"] is False
    assert summary["scanned"] == 1
    assert summary["actions"] == {"complete": 1}
    snapshot = ActivityQueue.for_session(folder).snapshot()
    assert snapshot[0].state is QueueState.COMPLETED


def test_recover_activity_queue_isolates_one_bad_session(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    _seed_committed_activity(sessions_root, "sess-good")
    # Claim an activity in a *second* session (so its lease store has an expired
    # lease worth recovering), then corrupt activities.json so reading it — the
    # step recover() takes only after finding an expired lease — raises.
    bad_folder = _seed_committed_activity(sessions_root, "sess-bad")
    (bad_folder / ".agent-lab" / "activities.json").write_text("not json", encoding="utf-8")

    summary = recover_activity_queue(sessions_root, reason="test", now=100.0)

    assert summary["scanned"] == 2
    assert summary["errors"] == 1
    assert summary["actions"] == {"complete": 1}


def test_recover_activity_queue_disabled_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ACTIVITY_QUEUE_RECOVERY", "0")
    sessions_root = tmp_path / "sessions"
    _seed_committed_activity(sessions_root, "sess-1")

    assert activity_queue_recovery_enabled() is False
    summary = recover_activity_queue(sessions_root, reason="test", now=100.0)
    assert summary["enabled"] is False
    assert "scanned" not in summary


def test_non_blocking_recover_skips_when_lock_held(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    _seed_committed_activity(sessions_root, "sess-1")

    with _flock(_lock_path(sessions_root), blocking=True) as acquired:
        assert acquired is True
        summary = recover_activity_queue(sessions_root, reason="periodic", now=100.0, blocking=False)

    assert summary["locked_out"] is True
    assert "scanned" not in summary
    # Nothing was touched while locked out — a later call still recovers it.
    follow_up = recover_activity_queue(sessions_root, reason="periodic", now=101.0, blocking=False)
    assert follow_up["locked_out"] is False
    assert follow_up["actions"] == {"complete": 1}


def test_recovery_due_throttles_by_interval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ACTIVITY_RECOVERY_INTERVAL_S", "60")
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()

    assert recovery_due(sessions_root, now=1000.0) is True

    recover_activity_queue(sessions_root, reason="test", now=1000.0)
    assert recovery_due(sessions_root, now=1030.0) is False
    assert recovery_due(sessions_root, now=1061.0) is True


def test_scheduler_tick_runs_activity_recovery_when_forced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.mission.scheduler as sched_mod

    sessions_root = tmp_path / "sessions"
    _seed_committed_activity(sessions_root, "sess-1")
    monkeypatch.setattr(sched_mod, "SESSIONS_DIR", sessions_root)

    result = sched_mod.scheduler_tick(sessions_dir=sessions_root, force=True)

    rec = result["activity_recovery"]
    assert rec is not None
    assert rec["scanned"] == 1
    assert rec["actions"] == {"complete": 1}
    snapshot = ActivityQueue.for_session(sessions_root / "sess-1").snapshot()
    assert snapshot[0].state is QueueState.COMPLETED


def test_scheduler_tick_skips_activity_recovery_when_not_due(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.mission.scheduler as sched_mod

    sessions_root = tmp_path / "sessions"
    _seed_committed_activity(sessions_root, "sess-1")
    monkeypatch.setattr(sched_mod, "SESSIONS_DIR", sessions_root)

    # First (forced) tick establishes last_run_at; the immediate follow-up
    # without force should skip because the interval hasn't elapsed.
    sched_mod.scheduler_tick(sessions_dir=sessions_root, force=True)
    result = sched_mod.scheduler_tick(sessions_dir=sessions_root, force=False)

    assert result["activity_recovery"] is None


def test_scheduler_tick_resolves_active_sessions_root_when_module_seam_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agent_lab.mission.scheduler as sched_mod
    import agent_lab.session.paths as session_paths

    sessions_root = tmp_path / "sessions"
    _seed_committed_activity(sessions_root, "sess-1")
    monkeypatch.setattr(sched_mod, "SESSIONS_DIR", None)
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", sessions_root)

    result = sched_mod.scheduler_tick(force=True)

    assert result["activity_recovery"] is not None
    assert result["activity_recovery"]["scanned"] == 1
    assert ActivityQueue.for_session(sessions_root / "sess-1").snapshot()[0].state is QueueState.COMPLETED
