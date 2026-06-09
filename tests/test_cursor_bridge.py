"""Cursor SDK bridge helper (no live bridge required)."""

from __future__ import annotations

import pytest

from agent_lab.cursor_bridge import (
    CursorBridgeUnavailable,
    cursor_bridge_failure_payload,
    cursor_sdk_client,
    format_cursor_connect_error,
    invalidate_workspace,
    is_transient_bridge_error,
)


def test_transient_bridge_error_includes_read_timeout():
    assert is_transient_bridge_error(RuntimeError("Bridge request timed out: ReadTimeout"))
    assert is_transient_bridge_error(RuntimeError("Connection refused"))


def test_format_connect_error_timeout_hint():
    msg = format_cursor_connect_error(RuntimeError("Bridge request timed out: ReadTimeout"))
    assert "재연결" in msg or "CURSOR" in msg


def test_format_connect_error_adds_hint():
    msg = format_cursor_connect_error(
        RuntimeError("Bridge request failed: ConnectError: [Errno 61] Connection refused")
    )
    assert "Connection refused" in msg
    assert "CURSOR_API_KEY" in msg


def test_invalidate_unknown_workspace_no_crash(tmp_path):
    invalidate_workspace(str(tmp_path))


def test_external_bridge_failure_does_not_auto_launch(monkeypatch, tmp_path):
    monkeypatch.setenv("CURSOR_SDK_BRIDGE_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("CURSOR_SDK_BRIDGE_TOKEN", "token")

    def fake_external_client() -> object:
        raise RuntimeError("Connection refused")

    def fake_launch(_workspace: str) -> object:
        raise AssertionError("external bridge failure must not auto-launch")

    monkeypatch.setattr("agent_lab.cursor_bridge._external_client", fake_external_client)
    monkeypatch.setattr("agent_lab.cursor_bridge._get_or_launch", fake_launch)

    with pytest.raises(CursorBridgeUnavailable) as excinfo:
        with cursor_sdk_client(str(tmp_path)):
            pass

    err = excinfo.value
    assert err.mode == "external"
    assert err.code == "cursor_bridge_external_unavailable"
    assert "Connection refused" in str(err)


def test_auto_bridge_failure_is_structured(monkeypatch, tmp_path):
    monkeypatch.delenv("CURSOR_SDK_BRIDGE_URL", raising=False)

    def fake_launch(_workspace: str) -> object:
        raise RuntimeError("bridge binary missing")

    monkeypatch.setattr("agent_lab.cursor_bridge._get_or_launch", fake_launch)

    with pytest.raises(CursorBridgeUnavailable) as excinfo:
        with cursor_sdk_client(str(tmp_path)):
            pass

    msg = format_cursor_connect_error(excinfo.value)
    payload = cursor_bridge_failure_payload(excinfo.value)
    assert "bridge binary missing" in msg
    assert payload["degraded"] is True
    assert "Codex/Claude" in str(payload["fallback"])
