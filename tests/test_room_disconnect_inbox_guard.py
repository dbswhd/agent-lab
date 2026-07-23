"""SSE client disconnect must not kill a worker mid a legitimate ask_human wait.

Regression for: a dropped SSE connection (tab backgrounded, laptop sleep,
network blip) while a human is still composing an ask_human answer used to
kill the Room subprocess immediately, orphaning the eventual human answer.
See sessions/2026-06-30-*token*-context*/{run.json,trace.jsonl}.
"""

from __future__ import annotations

import asyncio
import threading
import time

from agent_lab.run.control import clear_cancel, force_reset_run_lock, is_cancelled
from agent_lab.run.meta import read_run_meta, write_run_meta


def setup_function(_fn):
    clear_cancel()
    force_reset_run_lock()


def teardown_function(_fn):
    clear_cancel()
    force_reset_run_lock()


def test_pending_human_inbox_blocks_disconnect_kill(tmp_path):
    from app.server.routers.room import _session_has_pending_human_inbox

    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(
        folder,
        {
            "human_inbox": [
                {"id": "inbox-1", "kind": "question", "status": "pending"},
            ]
        },
    )
    assert _session_has_pending_human_inbox(folder) is True


def test_resolved_human_inbox_does_not_block_disconnect_kill(tmp_path):
    from app.server.routers.room import _session_has_pending_human_inbox

    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(
        folder,
        {
            "human_inbox": [
                {"id": "inbox-1", "kind": "question", "status": "resolved"},
                {"id": "inbox-2", "kind": "question", "status": "timeout"},
            ]
        },
    )
    assert _session_has_pending_human_inbox(folder) is False


def test_no_human_inbox_does_not_block_disconnect_kill(tmp_path):
    from app.server.routers.room import _session_has_pending_human_inbox

    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {})
    assert _session_has_pending_human_inbox(folder) is False


def test_none_folder_does_not_block_disconnect_kill():
    from app.server.routers.room import _session_has_pending_human_inbox

    assert _session_has_pending_human_inbox(None) is False


def test_pending_human_inbox_blocks_disconnect_kill_for_authority_cohort(tmp_path, monkeypatch):
    """Regression: AGENT_LAB_MISSION_AUTHORITY sessions store pending inbox items
    in the Mission journal only (human_inbox is popped from run.json) -- reading
    run.json["human_inbox"] directly always finds nothing and silently breaks the
    disconnect grace period for the live Wave B cohort."""
    from agent_lab.human_inbox import create_inbox_item
    from app.server.routers.room import _session_has_pending_human_inbox

    folder = tmp_path / "authority"
    folder.mkdir()
    write_run_meta(folder, {"topic": "ship"})
    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY_SESSIONS", "authority")

    create_inbox_item(folder, kind="question", source="test", prompt="Which scope?")

    assert "human_inbox" not in read_run_meta(folder)
    assert _session_has_pending_human_inbox(folder) is True


def test_resolved_human_inbox_does_not_block_disconnect_kill_for_authority_cohort(tmp_path, monkeypatch):
    from agent_lab.human_inbox import create_inbox_item, resolve_inbox_item
    from app.server.routers.room import _session_has_pending_human_inbox

    folder = tmp_path / "authority"
    folder.mkdir()
    write_run_meta(folder, {"topic": "ship"})
    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY_SESSIONS", "authority")

    item = create_inbox_item(folder, kind="question", source="test", prompt="Which scope?")
    resolve_inbox_item(folder, item["id"], decision="safe")

    assert _session_has_pending_human_inbox(folder) is False


def test_stream_cancel_requests_session_cancel_without_pending_human_inbox(tmp_path, monkeypatch):
    from app.server.routers.room import _cancel_room_stream_worker

    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {})
    calls = []

    def fake_global_cancel(cancel_folder):
        calls.append(cancel_folder)
        return {"ok": True}

    monkeypatch.setattr("agent_lab.mission.loop.on_global_run_cancel", fake_global_cancel)

    detached = _cancel_room_stream_worker(folder=folder, run_session_id="sess")

    assert detached is False
    assert is_cancelled("sess") is True
    assert calls == [folder]


def test_stream_cancel_detaches_when_human_inbox_is_pending(tmp_path, monkeypatch):
    from app.server.routers.room import _cancel_room_stream_worker

    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(
        folder,
        {
            "human_inbox": [
                {"id": "inbox-1", "kind": "question", "status": "pending"},
            ]
        },
    )
    calls = []

    def fake_global_cancel(cancel_folder):
        calls.append(cancel_folder)
        return {"ok": True}

    monkeypatch.setattr("agent_lab.mission.loop.on_global_run_cancel", fake_global_cancel)

    detached = _cancel_room_stream_worker(folder=folder, run_session_id="sess")

    assert detached is True
    assert is_cancelled("sess") is False
    assert calls == []


def test_wait_for_room_worker_cancel_ack_preserves_task_cancellation():
    from app.server.routers.room import _wait_for_room_worker_cancel_ack

    async def run_cancelled_wait():
        task = asyncio.current_task()
        assert task is not None
        worker = asyncio.get_running_loop().create_future()
        task.cancel()
        try:
            await _wait_for_room_worker_cancel_ack(worker)
        except asyncio.CancelledError:
            worker.cancel()
            return True
        return False

    assert asyncio.run(run_cancelled_wait()) is True


def test_room_run_stream_generator_detaches_when_existing_session_has_pending_human_inbox(tmp_path, monkeypatch):
    import agent_lab.session as session_mod
    import agent_lab.session.paths as session_paths
    import app.server.deps as deps_mod
    import app.server.routers.room as room_router

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    folder = sessions_dir / "sess"
    folder.mkdir()
    write_run_meta(
        folder,
        {
            "human_inbox": [
                {"id": "inbox-1", "kind": "question", "status": "pending"},
            ]
        },
    )
    started = threading.Event()
    release = threading.Event()

    def fake_continue_room_round(*_args, **_kwargs):
        started.set()
        release.wait(timeout=2.0)
        return [], "# plan"

    cancel_calls = []
    real_cancel_stream_worker = room_router._cancel_room_stream_worker

    def record_cancel_stream_worker(*, folder, run_session_id):
        cancel_calls.append((folder, run_session_id))
        return real_cancel_stream_worker(folder=folder, run_session_id=run_session_id)

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(room_router, "_agents_not_ready", lambda _agents: [])
    monkeypatch.setattr(room_router, "continue_room_round", fake_continue_room_round)
    monkeypatch.setattr(room_router, "_cancel_room_stream_worker", record_cancel_stream_worker)

    class DisconnectAfterStart:
        def __init__(self):
            self.calls = 0

        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 1

    async def run_stream_until_disconnect():
        response = await room_router.create_room_run(
            DisconnectAfterStart(),
            topic="continue pending human inbox",
            agents='["kimi_work"]',
            synthesize=False,
            synthesize_only=False,
            mode="discuss",
            session_id="sess",
            permissions="{}",
            skill_intent=None,
            agent_rounds=1,
            request_id=None,
            review_mode=False,
            consensus_mode=False,
            efficiency_mode=False,
            turn_profile="discuss",
            preset="",
            role_policy="",
            research_mode=False,
            workspace_id="agent-lab",
            workspace_path=None,
            session_template="general",
            agent_capabilities="{}",
            agent_thread_bindings="{}",
            room_models="",
            files=[],
        )
        stream = response.body_iterator
        first_chunk = await anext(stream)
        assert '"type": "start"' in first_chunk
        for _ in range(4):
            try:
                await anext(stream)
            except StopAsyncIteration:
                return
        raise AssertionError("stream should stop after simulated disconnect")

    try:
        asyncio.run(run_stream_until_disconnect())
    finally:
        release.set()

    assert is_cancelled("sess") is False
    assert cancel_calls == [(folder, "sess")]
    assert started.wait(timeout=1.0)
    deadline = time.time() + 2.0
    while time.time() < deadline:
        from agent_lab.run.control import run_lock_status

        if not run_lock_status()["locked"]:
            break
        time.sleep(0.05)

    from agent_lab.run.control import run_lock_status

    assert run_lock_status()["locked"] is False


def test_room_run_stream_generator_times_out_and_persists_partial_state(tmp_path, monkeypatch):
    import agent_lab.session as session_mod
    import agent_lab.session.paths as session_paths
    import app.server.deps as deps_mod
    import app.server.routers.room as room_router

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    folder = sessions_dir / "sess"
    folder.mkdir()
    write_run_meta(folder, {})
    started = threading.Event()
    release = threading.Event()

    def fake_continue_room_round(*_args, **_kwargs):
        started.set()
        release.wait(timeout=0.5)
        from agent_lab.run.meta import patch_run_meta

        patch_run_meta(folder, lambda meta: {**meta, "status": "cancelled"})
        return [], "# plan"

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(room_router, "_agents_not_ready", lambda _agents: [])
    monkeypatch.setattr(room_router, "continue_room_round", fake_continue_room_round)
    monkeypatch.setattr(room_router, "_room_server_timeout_sec", lambda: 0.01)

    class NeverDisconnected:
        async def is_disconnected(self):
            return False

    async def run_stream_until_timeout():
        response = await room_router.create_room_run(
            NeverDisconnected(),
            topic="server timeout partial state",
            agents='["kimi_work"]',
            synthesize=False,
            synthesize_only=False,
            mode="discuss",
            session_id="sess",
            permissions="{}",
            skill_intent=None,
            agent_rounds=1,
            request_id=None,
            review_mode=False,
            consensus_mode=False,
            efficiency_mode=False,
            turn_profile="discuss",
            preset="",
            role_policy="",
            research_mode=False,
            workspace_id="agent-lab",
            workspace_path=None,
            session_template="general",
            agent_capabilities="{}",
            agent_thread_bindings="{}",
            room_models="",
            files=[],
        )
        stream = response.body_iterator
        chunks = [await anext(stream)]
        async for chunk in stream:
            chunks.append(chunk)
        return chunks

    try:
        chunks = asyncio.run(run_stream_until_timeout())
    finally:
        release.set()

    joined = "".join(chunks)
    assert started.wait(timeout=1.0)
    assert '"type": "run_timeout"' in joined
    assert '"status": "partial"' in joined
    assert '"cancelled": true' in joined
    assert is_cancelled("sess") is True

    run_meta = read_run_meta(folder)
    assert run_meta["status"] == "partial"
    assert run_meta["room_timeout"]["reason"] == "server_timeout"
    assert run_meta["room_timeout"]["timeout_sec"] == 0.01
    assert '"type": "complete"' in joined
    assert '"status": "partial"' in joined.rsplit('"type": "complete"', 1)[-1]
