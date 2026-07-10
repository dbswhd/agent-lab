"""Live Room SSE append-only log."""

from __future__ import annotations

from pathlib import Path

from agent_lab.room.live_log import (
    append_live_room_event,
    archive_live_room_log,
    clear_live_room_log,
    read_archived_live_room_logs,
    read_live_room_log,
    read_session_live_log,
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


def test_live_room_log_archive_and_read_session(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    append_live_room_event(folder, "agent_start", {"agent": "codex", "round": 1})
    append_live_room_event(
        folder,
        "agent_activity",
        {"agent": "codex", "round": 1, "text": "thinking"},
    )
    archive_live_room_log(folder, 1)
    assert read_live_room_log(folder) == []
    archived = read_archived_live_room_logs(folder)
    assert len(archived) == 2
    assert archived[0]["type"] == "agent_start"
    append_live_room_event(folder, "agent_start", {"agent": "claude", "round": 1})
    merged = read_session_live_log(folder)
    assert len(merged) == 3
    assert merged[-1]["agent"] == "claude"


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


def test_session_detail_pages_chat_without_bulk_read(tmp_path: Path, monkeypatch) -> None:
    from app.server import deps
    from app.server import session_helpers

    folder = tmp_path / "2026-paged-chat"
    folder.mkdir()
    (folder / "topic.txt").write_text("t\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        '{"index": 0}\n\n{"index": 1}\n{"index": 2}\n',
        encoding="utf-8",
    )

    original_read_text = Path.read_text

    def reject_bulk_chat_read(path: Path, *args, **kwargs):
        if path == folder / "chat.jsonl":
            raise AssertionError("chat pagination must stream instead of bulk-reading")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_bulk_chat_read)
    monkeypatch.setattr(deps, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(session_helpers, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(session_helpers, "gc_stale_worktrees", lambda *_a, **_k: None)

    detail = deps.session_detail(folder.name, chat_limit=1, chat_offset=1)

    assert detail["chat_total"] == 3
    assert detail["chat"] == [{"index": 1}]
