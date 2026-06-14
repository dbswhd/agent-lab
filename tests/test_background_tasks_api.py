"""Tests for background task API (Phase 3)."""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from unittest.mock import patch

from fastapi.testclient import TestClient


@contextmanager
def _make_session(tmp_path: Path) -> Generator[tuple[TestClient, str], None, None]:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_id = "test-bgtask-session"
    session_dir = sessions_dir / session_id
    session_dir.mkdir()
    (session_dir / "run.json").write_text("{}", encoding="utf-8")

    # Fresh task manager per test to avoid cross-test state
    import agent_lab.background_tasks as bgt_mod

    original_manager = bgt_mod._manager
    bgt_mod._manager = None

    import app.server.routers.background_tasks as router_mod

    original_loaded = router_mod._loaded_sessions.copy()
    router_mod._loaded_sessions.clear()

    with (
        patch("app.server.deps.SESSIONS_DIR", sessions_dir),
        patch("agent_lab.workspace_files.SESSIONS_DIR", sessions_dir),
    ):
        from app.server.main import app

        with TestClient(app, raise_server_exceptions=True) as client:
            yield client, session_id

    # Restore
    bgt_mod._manager = original_manager
    router_mod._loaded_sessions.clear()
    router_mod._loaded_sessions.update(original_loaded)


# ── Submit + list ─────────────────────────────────────────────────────────────


def test_submit_and_list(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.post(
            f"/api/sessions/{sid}/bg-tasks",
            json={"label": "echo test", "command": [sys.executable, "-c", "print('hello')"]},
        )
        assert r.status_code == 200
        task = r.json()
        assert task["status"] in ("queued", "running", "done")
        assert task["label"] == "echo test"
        task_id = task["task_id"]

        # List
        r2 = client.get(f"/api/sessions/{sid}/bg-tasks")
        assert r2.status_code == 200
        tasks = r2.json()["tasks"]
        assert any(t["task_id"] == task_id for t in tasks)


def test_get_task(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.post(
            f"/api/sessions/{sid}/bg-tasks",
            json={"label": "noop", "command": [sys.executable, "-c", ""]},
        )
        task_id = r.json()["task_id"]

        r2 = client.get(f"/api/sessions/{sid}/bg-tasks/{task_id}")
        assert r2.status_code == 200
        assert r2.json()["task_id"] == task_id


def test_task_produces_log(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.post(
            f"/api/sessions/{sid}/bg-tasks",
            json={
                "label": "hello",
                "command": [sys.executable, "-c", "print('hello world')"],
            },
        )
        task_id = r.json()["task_id"]

        # Wait for completion (up to 5 s)
        for _ in range(50):
            status = client.get(f"/api/sessions/{sid}/bg-tasks/{task_id}").json()["status"]
            if status in ("done", "failed"):
                break
            time.sleep(0.1)

        log_r = client.get(f"/api/sessions/{sid}/bg-tasks/{task_id}/log")
        assert log_r.status_code == 200
        lines = log_r.json()["lines"]
        assert any("hello world" in (ln.get("text", "")) for ln in lines)


def test_task_done_exit_code_zero(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.post(
            f"/api/sessions/{sid}/bg-tasks",
            json={"label": "ok", "command": [sys.executable, "-c", ""]},
        )
        task_id = r.json()["task_id"]
        for _ in range(50):
            t = client.get(f"/api/sessions/{sid}/bg-tasks/{task_id}").json()
            if t["status"] == "done":
                assert t["exit_code"] == 0
                break
            time.sleep(0.1)


def test_task_failed_non_zero(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.post(
            f"/api/sessions/{sid}/bg-tasks",
            json={"label": "fail", "command": [sys.executable, "-c", "raise SystemExit(1)"]},
        )
        task_id = r.json()["task_id"]
        for _ in range(50):
            t = client.get(f"/api/sessions/{sid}/bg-tasks/{task_id}").json()
            if t["status"] == "failed":
                assert t["exit_code"] == 1
                break
            time.sleep(0.1)


# ── Cancel ────────────────────────────────────────────────────────────────────


def test_cancel_running_task(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.post(
            f"/api/sessions/{sid}/bg-tasks",
            json={
                "label": "sleep",
                "command": [sys.executable, "-c", "import time; time.sleep(60)"],
            },
        )
        task_id = r.json()["task_id"]
        # Wait until running
        for _ in range(20):
            if client.get(f"/api/sessions/{sid}/bg-tasks/{task_id}").json()["status"] == "running":
                break
            time.sleep(0.05)

        r2 = client.delete(f"/api/sessions/{sid}/bg-tasks/{task_id}")
        assert r2.status_code == 200
        assert r2.json()["cancelled"] is True

        time.sleep(0.2)
        status = client.get(f"/api/sessions/{sid}/bg-tasks/{task_id}").json()["status"]
        assert status == "cancelled"


# ── Validation ────────────────────────────────────────────────────────────────


def test_empty_command_rejected(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.post(
            f"/api/sessions/{sid}/bg-tasks",
            json={"label": "bad", "command": []},
        )
        assert r.status_code == 422


def test_unknown_session_404(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, _):
        r = client.get("/api/sessions/no-such-session/bg-tasks")
        assert r.status_code == 404


def test_unknown_task_404(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.get(f"/api/sessions/{sid}/bg-tasks/nonexistent")
        assert r.status_code == 404


# ── Log offset ────────────────────────────────────────────────────────────────


def test_log_offset(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.post(
            f"/api/sessions/{sid}/bg-tasks",
            json={
                "label": "multiline",
                "command": [sys.executable, "-c", "print('a'); print('b'); print('c')"],
            },
        )
        task_id = r.json()["task_id"]
        for _ in range(50):
            if client.get(f"/api/sessions/{sid}/bg-tasks/{task_id}").json()["status"] == "done":
                break
            time.sleep(0.1)

        all_lines = client.get(f"/api/sessions/{sid}/bg-tasks/{task_id}/log").json()["lines"]
        assert len(all_lines) >= 3

        partial = client.get(f"/api/sessions/{sid}/bg-tasks/{task_id}/log?offset=1").json()["lines"]
        assert len(partial) == len(all_lines) - 1
