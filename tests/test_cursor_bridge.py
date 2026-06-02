"""Cursor SDK bridge helper (no live bridge required)."""

from __future__ import annotations

from agent_lab.cursor_bridge import format_cursor_connect_error, invalidate_workspace


def test_format_connect_error_adds_hint():
    msg = format_cursor_connect_error(
        RuntimeError("Bridge request failed: ConnectError: [Errno 61] Connection refused")
    )
    assert "Connection refused" in msg
    assert "CURSOR_API_KEY" in msg


def test_invalidate_unknown_workspace_no_crash(tmp_path):
    invalidate_workspace(str(tmp_path))
