"""Live Room SSE append-only log."""

from __future__ import annotations

from pathlib import Path

from agent_lab.room.live_log import (
    append_live_room_event,
    clear_live_room_log,
    read_live_room_log,
)


def test_live_room_log_append_and_read(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    append_live_room_event(folder, "agent_token", {"agent": "claude", "round": 1, "text": "Hi"})
    append_live_room_event(folder, "noop_ignored", {"x": 1})
    rows = read_live_room_log(folder)
    assert len(rows) == 1
    assert rows[0]["type"] == "agent_token"
    assert rows[0]["text"] == "Hi"


def test_live_room_log_clear(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    append_live_room_event(folder, "agent_start", {"agent": "codex", "round": 1})
    clear_live_room_log(folder)
    assert read_live_room_log(folder) == []


def test_session_detail_includes_live_log(tmp_path: Path, monkeypatch) -> None:
    from app.server import deps
    from app.server import session_helpers

    folder = tmp_path / "2026-test-live"
    folder.mkdir()
    (folder / "topic.txt").write_text("t\n", encoding="utf-8")
    (folder / "meta.json").write_text("{}", encoding="utf-8")
    append_live_room_event(folder, "agent_token", {"agent": "claude", "text": "x"})

    monkeypatch.setattr(deps, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(session_helpers, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(session_helpers, "gc_stale_worktrees", lambda *_a, **_k: None)
    detail = deps.session_detail(folder.name)
    assert detail["live_log"]
    assert detail["live_log"][0]["text"] == "x"
