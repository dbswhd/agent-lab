"""Cursor SDK bridge helper (no live bridge required)."""

from __future__ import annotations

import pytest

from agent_lab.cursor.bridge import (
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

    monkeypatch.setattr("agent_lab.cursor.bridge._external_client", fake_external_client)
    monkeypatch.setattr("agent_lab.cursor.bridge._get_or_launch", fake_launch)

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

    monkeypatch.setattr("agent_lab.cursor.bridge._get_or_launch", fake_launch)

    with pytest.raises(CursorBridgeUnavailable) as excinfo:
        with cursor_sdk_client(str(tmp_path)):
            pass

    msg = format_cursor_connect_error(excinfo.value)
    payload = cursor_bridge_failure_payload(excinfo.value)
    assert "bridge binary missing" in msg
    assert payload["degraded"] is True
    assert "Codex/Claude" in str(payload["fallback"])


def test_cursor_model_selection_splits_composite_effort_suffix():
    """CURSOR_MODEL stores "<base>-<effort>" (model_prefs._cursor_compose), but
    the live Cursor API rejects that composite string as a model id — effort
    must travel as a ModelSelection param instead (grok-4.5-high 422:
    "Cannot use this model: grok-4.5-high")."""
    from agent_lab.cursor.provider import _cursor_model_selection

    class _FakeParam:
        def __init__(self, *, id: str, value: str) -> None:
            self.id = id
            self.value = value

    class _FakeSelection:
        def __init__(self, *, id: str, params: list) -> None:
            self.id = id
            self.params = params

    result = _cursor_model_selection("grok-4.5-high", selection_cls=_FakeSelection, param_cls=_FakeParam)
    assert isinstance(result, _FakeSelection)
    assert result.id == "grok-4.5"
    assert len(result.params) == 1
    assert result.params[0].id == "effort"
    assert result.params[0].value == "high"


def test_cursor_model_selection_passes_through_plain_model_id():
    from agent_lab.cursor.provider import _cursor_model_selection

    class _FakeParam:
        def __init__(self, *, id: str, value: str) -> None:
            pass

    class _FakeSelection:
        def __init__(self, *, id: str, params: list) -> None:
            pass

    result = _cursor_model_selection("grok-4.5", selection_cls=_FakeSelection, param_cls=_FakeParam)
    assert result == "grok-4.5"


def test_cursor_model_selection_falls_back_to_base_id_without_sdk_types():
    """When cursor_sdk isn't installed (selection_cls/param_cls are None), the
    effort tier is dropped rather than sent as an invalid composite string."""
    from agent_lab.cursor.provider import _cursor_model_selection

    result = _cursor_model_selection("grok-4.5-high", selection_cls=None, param_cls=None)
    assert result == "grok-4.5"
