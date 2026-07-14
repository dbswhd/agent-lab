"""P1: resume/reattach to a Room SSE stream after a client disconnect.

Covers ``_room_resume_events`` (the pollable generator behind
``GET /api/room/runs/{session_id}/resume``) and
``_terminal_event_from_persisted_state`` — the two pieces that let a
reconnecting client replay missed live-log rows and then either keep
tailing a still-running turn or receive a synthesized terminal event for
one that already finished (possibly while the client was disconnected).
"""

from __future__ import annotations

import asyncio

import pytest

from agent_lab.room.live_log import append_live_room_event
from agent_lab.run.control import clear_cancel, end_run, force_reset_run_lock, try_begin_run
from agent_lab.run.meta import write_run_meta

from app.server.routers.room import _room_resume_events, _terminal_event_from_persisted_state


def _drain(agen):
    async def _run():
        out = []
        async for item in agen:
            out.append(item)
        return out

    return asyncio.run(_run())


@pytest.fixture(autouse=True)
def _isolate_run_lock(tmp_path, monkeypatch: pytest.MonkeyPatch):
    # try_begin_run() holds a real cross-process fcntl lock at
    # config_dir()/run.lock; without a private dir per test, concurrent
    # xdist workers can race on the same shared machine-wide lock file (see
    # tests/test_run_control.py's _isolate_run_lock for the full story).
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(tmp_path / ".agent-lab-config"))


def setup_function(_fn):
    clear_cancel()
    force_reset_run_lock()


def teardown_function(_fn):
    clear_cancel()
    force_reset_run_lock()


def test_resume_replays_backlog_then_terminal_state_when_not_locked(tmp_path):
    folder = tmp_path / "sess"
    folder.mkdir()
    append_live_room_event(folder, "agent_start", {"agent": "claude"})
    append_live_room_event(folder, "agent_token", {"agent": "claude", "text": "hi"})
    append_live_room_event(folder, "agent_done", {"agent": "claude", "content": "hi"})
    write_run_meta(folder, {"status": "completed", "turns": [{"failed_agents": [], "succeeded_agents": ["claude"]}]})

    async def not_disconnected():
        return False

    events = _drain(_room_resume_events(folder, "sess", since=0, is_disconnected=not_disconnected, poll_sec=0.01))
    types = [e["type"] for e in events if e is not None]
    assert types == ["agent_start", "agent_token", "agent_done", "complete"]
    complete = events[-1]
    assert complete["resumed"] is True
    assert complete["status"] == "completed"
    assert complete["succeeded_agents"] == ["claude"]


def test_resume_since_cursor_skips_already_seen_rows(tmp_path):
    folder = tmp_path / "sess"
    folder.mkdir()
    append_live_room_event(folder, "agent_start", {"agent": "claude"})
    append_live_room_event(folder, "agent_token", {"agent": "claude", "text": "hi"})
    write_run_meta(folder, {"status": "completed"})

    async def not_disconnected():
        return False

    events = _drain(_room_resume_events(folder, "sess", since=1, is_disconnected=not_disconnected, poll_sec=0.01))
    types = [e["type"] for e in events]
    assert types == ["agent_token", "complete"]


def test_resume_synthesizes_cancelled_terminal_state(tmp_path):
    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {"status": "cancelled"})

    async def not_disconnected():
        return False

    events = _drain(_room_resume_events(folder, "sess", since=0, is_disconnected=not_disconnected, poll_sec=0.01))
    types = [e["type"] for e in events]
    assert types == ["run_cancelled", "complete"]
    assert events[-1]["cancelled"] is True


def test_resume_synthesizes_failed_terminal_state(tmp_path):
    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {"status": "failed"})

    async def not_disconnected():
        return False

    events = _drain(_room_resume_events(folder, "sess", since=0, is_disconnected=not_disconnected, poll_sec=0.01))
    assert [e["type"] for e in events] == ["run_failed", "error"]


def test_resume_returns_immediately_when_client_already_gone(tmp_path):
    folder = tmp_path / "sess"
    folder.mkdir()
    append_live_room_event(folder, "agent_start", {"agent": "claude"})
    write_run_meta(folder, {"status": "completed"})

    async def already_disconnected():
        return True

    events = _drain(_room_resume_events(folder, "sess", since=0, is_disconnected=already_disconnected, poll_sec=0.01))
    assert events == []


def test_resume_tails_live_updates_while_run_lock_held(tmp_path):
    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {"status": "completed"})
    assert try_begin_run(session_id="sess", run_kind="room")
    try:
        append_live_room_event(folder, "agent_start", {"agent": "claude"})

        calls = {"n": 0}

        async def disconnect_after_two_polls():
            calls["n"] += 1
            if calls["n"] == 2:
                append_live_room_event(folder, "agent_token", {"agent": "claude", "text": "more"})
            return calls["n"] > 3

        events = _drain(
            _room_resume_events(folder, "sess", since=0, is_disconnected=disconnect_after_two_polls, poll_sec=0.01)
        )
        types = [e["type"] for e in events if e is not None]
        # Still locked for the whole run → no terminal event synthesized;
        # both the initial backlog row and the row appended mid-poll show up.
        assert types == ["agent_start", "agent_token"]
    finally:
        end_run()
        force_reset_run_lock()


def test_terminal_event_partial_status(tmp_path):
    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(
        folder,
        {"status": "partial", "turns": [{"failed_agents": ["codex"], "succeeded_agents": ["claude"]}]},
    )
    events = _terminal_event_from_persisted_state(folder, "sess")
    assert events[0]["type"] == "complete"
    assert events[0]["status"] == "partial"
    assert events[0]["failed_agents"] == ["codex"]
    assert events[0]["succeeded_agents"] == ["claude"]


@pytest.fixture
def resume_api_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_id = "resume-sess"
    folder = sessions_dir / session_id
    folder.mkdir()
    append_live_room_event(folder, "agent_start", {"agent": "claude"})
    append_live_room_event(folder, "agent_done", {"agent": "claude", "content": "hi"})
    write_run_meta(folder, {"status": "completed"})

    import agent_lab.session.paths as sp

    monkeypatch.setattr(sp, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr("app.server.session_helpers.SESSIONS_DIR", sessions_dir)

    from app.server.main import create_app

    return TestClient(create_app(bootstrap=False)), session_id


def test_resume_endpoint_http_replays_and_completes(resume_api_client):
    client, session_id = resume_api_client
    res = client.get(f"/api/room/runs/{session_id}/resume", params={"since": 0})
    assert res.status_code == 200
    events = [line[len("data: ") :] for line in res.text.splitlines() if line.startswith("data: ")]
    import json as _json

    types = [_json.loads(e)["type"] for e in events]
    assert types == ["agent_start", "agent_done", "complete"]


def test_resume_endpoint_http_404_for_unknown_session(resume_api_client):
    client, _session_id = resume_api_client
    res = client.get("/api/room/runs/does-not-exist/resume")
    assert res.status_code == 404
