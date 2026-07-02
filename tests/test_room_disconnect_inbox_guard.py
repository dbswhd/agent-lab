"""SSE client disconnect must not kill a worker mid a legitimate ask_human wait.

Regression for: a dropped SSE connection (tab backgrounded, laptop sleep,
network blip) while a human is still composing an ask_human answer used to
kill the Room subprocess immediately, orphaning the eventual human answer.
See sessions/2026-06-30-*token*-context*/{run.json,trace.jsonl}.
"""

from __future__ import annotations

from agent_lab.run.meta import write_run_meta


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
