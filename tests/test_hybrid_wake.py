"""Hybrid cloud wake — relay envelope hint + mission-wake hook."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from agent_lab.gateway.config import save_gateway_config
from agent_lab.gateway.hybrid_relay import (
    deliver_hybrid_relay,
    request_scheduler_wake,
    should_hybrid_wake,
    verify_wake_request,
    wake_hint_for_envelope,
    wake_events_for,
)
from app.server.main import app
from tests.http_server_helpers import (
    read_post_body,
    start_local_http_server,
    stop_local_http_server,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def gateway_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "gateway.toml"
    monkeypatch.setenv("AGENT_LAB_GATEWAY_CONFIG", str(path))
    return path


def test_wake_events_defaults() -> None:
    assert "schedule_tick" in wake_events_for({})
    assert "auto_merge_blocked" in wake_events_for({})


def test_should_hybrid_wake_requires_offline_and_url() -> None:
    hybrid = {"wake_url": "https://tunnel/hooks/mission-wake", "wake_enabled": True}
    assert should_hybrid_wake(hybrid, event="schedule_tick", daemon_online=False) is True
    assert should_hybrid_wake(hybrid, event="schedule_tick", daemon_online=True) is False
    assert should_hybrid_wake(hybrid, event="inbox_pending", daemon_online=False) is False
    assert should_hybrid_wake({**hybrid, "wake_enabled": False}, event="schedule_tick", daemon_online=False) is False


def test_wake_hint_for_envelope() -> None:
    hybrid = {"wake_url": "https://tunnel/wake", "wake_enabled": True}
    hint = wake_hint_for_envelope(hybrid, event="merge_ready", online=False)
    assert hint == {
        "attempt": True,
        "url": "https://tunnel/wake",
        "method": "POST",
        "event": "merge_ready",
    }
    assert wake_hint_for_envelope(hybrid, event="merge_ready", online=True) is None


def test_deliver_hybrid_relay_includes_wake_hint(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_config,
) -> None:
    received: list[bytes] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(read_post_body(self))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args):
            return

    server, port, thread = start_local_http_server(Handler)
    try:
        wake_url = "https://tunnel.example/api/hooks/mission-wake"
        save_gateway_config(
            {
                "hybrid": {
                    "enabled": True,
                    "relay_url": f"http://127.0.0.1:{port}/relay",
                    "wake_url": wake_url,
                    "wake_enabled": True,
                },
            }
        )
        monkeypatch.setenv("AGENT_LAB_DAEMON_STATE", str(tmp_path / "missing_daemon.json"))

        result = deliver_hybrid_relay("schedule_tick", {"schedule_id": "s1"})
        assert result.get("ok") is True
        assert received
        body = json.loads(received[0].decode("utf-8"))
        assert body["daemon_online"] is False
        assert body["wake"]["url"] == wake_url
        assert body["wake"]["event"] == "schedule_tick"
    finally:
        stop_local_http_server(server, thread)


def test_verify_wake_request_scheduler_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_SCHEDULER_HOOK_TOKEN", "secret-token")
    assert verify_wake_request({"X-Agent-Lab-Scheduler-Token": "secret-token"}) is True
    assert verify_wake_request({"X-Agent-Lab-Scheduler-Token": "wrong"}) is False


def test_mission_wake_hook_triggers_scheduler_tick(
    client: TestClient,
    gateway_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_SCHEDULER_HOOK_TOKEN", "wake-me")
    tick = {"ok": True, "runs": [{"schedule_id": "daily"}]}
    mock_tick = MagicMock(return_value=tick)
    monkeypatch.setattr("agent_lab.mission_scheduler.scheduler_tick", mock_tick)

    r = client.post(
        "/api/hooks/mission-wake",
        headers={"X-Agent-Lab-Scheduler-Token": "wake-me"},
        json={},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["wake"] is True
    mock_tick.assert_called_once_with(force=True)


def test_mission_wake_hook_rejects_bad_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_SCHEDULER_HOOK_TOKEN", "wake-me")
    r = client.post("/api/hooks/mission-wake", json={})
    assert r.status_code == 401


def test_request_scheduler_wake_posts_token(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_config,
) -> None:
    captured: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            read_post_body(self)
            captured["token"] = self.headers.get("X-Agent-Lab-Scheduler-Token", "")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *_args):
            return

    server, port, thread = start_local_http_server(Handler)
    try:
        wake_url = f"http://127.0.0.1:{port}/wake"
        save_gateway_config({"hybrid": {"wake_url": wake_url}})
        monkeypatch.setenv("AGENT_LAB_SCHEDULER_HOOK_TOKEN", "tok123")

        result = request_scheduler_wake()
        assert result.get("ok") is True
        assert captured.get("token") == "tok123"
    finally:
        stop_local_http_server(server, thread)
