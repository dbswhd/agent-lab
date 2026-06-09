"""MB-11 — Codex openai-oauth proxy transport."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_lab.runtime.adapters.codex import (
    can_route_codex_proxy,
    codex_proxy_enabled,
    invoke_codex_proxy,
    probe_codex_proxy,
)


def test_codex_proxy_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_CODEX_PROXY", raising=False)
    assert codex_proxy_enabled() is False
    assert can_route_codex_proxy() is False


def test_can_route_blocks_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CODEX_PROXY", "1")
    assert can_route_codex_proxy(inbox_mcp=True) is False
    assert can_route_codex_proxy(execute_plugins=True) is False
    assert can_route_codex_proxy() is True


def test_probe_codex_proxy_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CODEX_PROXY", "1")
    monkeypatch.setenv("AGENT_LAB_CODEX_PROXY_URL", "http://127.0.0.1:10531/v1")

    class _Resp:
        def read(self) -> bytes:
            return json.dumps({"data": [{"id": "gpt-5.3-codex"}]}).encode()

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    payload = probe_codex_proxy()
    assert payload["enabled"] is True
    assert payload["ok"] is True


def test_invoke_codex_proxy_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CODEX_PROXY", "1")

    body = json.dumps(
        {
            "choices": [
                {"message": {"content": "proxy says hello"}},
            ]
        }
    ).encode()

    class _Resp:
        def read(self) -> bytes:
            return body

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    text = invoke_codex_proxy("sys", "user")
    assert text == "proxy says hello"


def test_codex_cli_routes_to_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CODEX_PROXY", "1")
    called: dict[str, str] = {}

    def _proxy(system: str, user: str, **kwargs: Any) -> str:
        called["system"] = system
        called["user"] = user
        return "via-proxy"

    monkeypatch.setattr(
        "agent_lab.runtime.adapters.codex.invoke_codex_proxy",
        _proxy,
    )
    from agent_lab.codex_cli import invoke

    assert invoke("sys", "user", room_turn=True) == "via-proxy"
    assert "sys" in called["system"]
    assert "Room turn" in called["user"] or "group debate" in called["user"]
