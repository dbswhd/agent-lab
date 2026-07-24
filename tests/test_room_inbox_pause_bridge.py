"""Layer A: cross-process Human Inbox creation → live ``inbox_pause`` signal.

``create_inbox_item()`` (src/agent_lab/human_inbox.py) always appends an
``item_id``-bearing ``inbox_pending`` row to ``live.jsonl``, regardless of
which OS process calls it — including the ``agent-lab-inbox`` MCP stdio
server, a separate process from the Room turn's own SSE-serving request.
``_new_cross_process_inbox_pause_events`` tails that file and synthesizes the
same ``inbox_pause`` signal the in-process ``decision-fork`` harvest path
already fires directly (see ``room/consensus_rounds.py``), so the browser's
"Discuss blocked" banner shows up in real time no matter which path created
the item.
"""

from __future__ import annotations

from pathlib import Path

from agent_lab.human_inbox import create_inbox_item
from agent_lab.room.live_log import append_live_room_event

from app.server.routers.room import _new_cross_process_inbox_pause_events


def test_detects_item_id_bearing_inbox_pending_row(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    append_live_room_event(
        folder,
        "inbox_pending",
        {"item_id": "inbox-x", "kind": "question", "source": "mcp_ask_human"},
    )

    events, cursor = _new_cross_process_inbox_pause_events(folder, 0)

    assert len(events) == 1
    assert events[0]["type"] == "inbox_pause"
    assert events[0]["reason"] == "inbox_pending"
    assert events[0]["item_id"] == "inbox-x"
    assert events[0]["kind"] == "question"
    assert events[0]["source"] == "mcp_ask_human"
    assert cursor == 1


def test_ignores_clarify_marker_row_without_item_id(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    # Matches the exact shape room/plan_scribe.py:237 and room/turn_policy.py:542
    # emit — a CLARIFY-phase marker, not an inbox item creation.
    append_live_room_event(folder, "inbox_pending", {"phase": "CLARIFY"})

    events, cursor = _new_cross_process_inbox_pause_events(folder, 0)

    assert events == []
    assert cursor == 1


def test_cursor_dedupes_across_polls(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    append_live_room_event(folder, "inbox_pending", {"item_id": "inbox-x"})

    first_events, cursor = _new_cross_process_inbox_pause_events(folder, 0)
    assert len(first_events) == 1

    second_events, cursor2 = _new_cross_process_inbox_pause_events(folder, cursor)
    assert second_events == []
    assert cursor2 == cursor


def test_ignores_unrelated_event_types(tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    append_live_room_event(folder, "agent_start", {"agent": "claude"})
    append_live_room_event(folder, "tool_start", {"agent": "claude", "tool": "Read"})

    events, cursor = _new_cross_process_inbox_pause_events(folder, 0)

    assert events == []
    assert cursor == 2


def test_real_create_inbox_item_call_is_detected(tmp_path: Path):
    """Integration-level: exercise the actual production call site (MCP
    ask_human path) rather than a hand-built live.jsonl row."""
    folder = tmp_path / "sess"
    folder.mkdir()

    item = create_inbox_item(
        folder,
        kind="question",
        source="mcp_ask_human",
        prompt="Scope?",
        options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
    )

    events, cursor = _new_cross_process_inbox_pause_events(folder, 0)

    assert len(events) == 1
    assert events[0]["item_id"] == item["id"]
    assert events[0]["source"] == "mcp_ask_human"
    assert cursor == 1
