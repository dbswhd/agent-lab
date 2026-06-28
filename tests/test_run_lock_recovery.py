"""run-lock blocked-path structured recovery signal tests.

Mock-only: run_lock_recovery_hint state matrix + the SSE run-start blocked path
emitting run_lock_blocked alongside the existing error event. The lock policy
itself is untouched; releasable follows the existing conservative rule.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")

from agent_lab.run import control as rc


@pytest.fixture(autouse=True)
def _reset_lock():
    rc.force_reset_run_lock()
    yield
    rc.force_reset_run_lock()


# --- run_lock_recovery_hint state matrix ----------------------------------


def test_hint_unlocked_is_releasable():
    h = rc.run_lock_recovery_hint()
    assert h["locked"] is False
    assert h["active_workers"] == 0
    assert h["releasable"] is True
    assert "release_lock" in h["action"]


def test_hint_locked_active_fresh_not_releasable():
    assert rc.try_begin_run() is True
    try:
        h = rc.run_lock_recovery_hint()
        assert h["locked"] is True
        assert h["active_workers"] == 1
        assert h["releasable"] is False  # genuinely active run — never force-release
        assert "wait_or_cancel" in h["action"]
    finally:
        rc.end_run()


def test_hint_locked_stale_is_releasable():
    assert rc.try_begin_run() is True
    try:
        rc._run_started_at = time.time() - (rc.RUN_LOCK_STALE_SEC + 10)
        h = rc.run_lock_recovery_hint()
        assert h["locked"] is True
        assert h["releasable"] is True
        assert h["age_sec"] is not None and h["age_sec"] >= rc.RUN_LOCK_STALE_SEC
    finally:
        rc.end_run()


def test_hint_locked_orphan_zero_workers_is_releasable():
    # crashed worker: lock held but no active worker counted
    assert rc.try_begin_run() is True
    rc._run_active = 0
    rc._run_started_at = time.time()
    try:
        h = rc.run_lock_recovery_hint()
        assert h["locked"] is True
        assert h["active_workers"] == 0
        assert h["releasable"] is True
    finally:
        rc.force_reset_run_lock()


def test_hint_shape_keys():
    h = rc.run_lock_recovery_hint()
    assert set(h) == {"locked", "age_sec", "active_workers", "releasable", "action"}


# --- SSE blocked path integration -----------------------------------------


@pytest.mark.integration
def test_sse_run_start_blocked_emits_run_lock_blocked_then_error():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server.main import app

    # Hold the lock with an active (fresh) worker so orphan-release won't free it.
    assert rc.try_begin_run() is True
    try:
        client = TestClient(app)
        res = client.post("/api/runs", json={"topic": "blocked by held lock"})
        assert res.status_code == 200
        body = res.text
        # structured recovery signal emitted, plus the legacy error for back-compat
        assert "run_lock_blocked" in body
        assert "a run is already in progress" in body
    finally:
        rc.end_run()


@pytest.mark.integration
def test_release_lock_endpoint_still_works():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server.main import app

    client = TestClient(app)
    res = client.post("/api/room/runs/release-lock")
    assert res.status_code == 200
    assert res.json()["ok"] is True
