"""Tunnel + launchd soak — integration + optional live Tier E."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from agent_lab.gateway.config import save_gateway_config
from agent_lab.gateway.hybrid_relay import deliver_hybrid_relay
from agent_lab.live_tunnel_launchd_soak import (
    check_hybrid_wake_hint,
    launchd_agent_loaded,
    run_live_tunnel_launchd_soak,
)
from app.server.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def gateway_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "gateway.toml"
    monkeypatch.setenv("AGENT_LAB_GATEWAY_CONFIG", str(path))
    return path


def test_check_hybrid_wake_hint() -> None:
    url = "https://tunnel.example/api/hooks/mission-wake"
    assert check_hybrid_wake_hint(wake_url=url) is True


def test_tunnel_launchd_soak_integration(
    client: TestClient,
    gateway_config,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI-safe: mission-wake hook + hybrid relay envelope wake hint."""
    monkeypatch.setenv("AGENT_LAB_SCHEDULER_HOOK_TOKEN", "soak-token")
    monkeypatch.setenv("AGENT_LAB_DAEMON_STATE", str(tmp_path / "offline_daemon.json"))

    received: list[bytes] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            received.append(self.rfile.read(length))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    wake_url = "http://127.0.0.1:8765/api/hooks/mission-wake"
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

    tick = {"ok": True, "runs": []}
    mock_tick = MagicMock(return_value=tick)
    monkeypatch.setattr("agent_lab.mission.scheduler.scheduler_tick", mock_tick)

    r = client.post(
        "/api/hooks/mission-wake",
        headers={"X-Agent-Lab-Scheduler-Token": "soak-token"},
        json={},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["wake"] is True
    mock_tick.assert_called_once_with(force=True)

    result = deliver_hybrid_relay("schedule_tick", {"schedule_id": "soak"})
    assert result.get("ok") is True
    assert received
    envelope = json.loads(received[0].decode("utf-8"))
    assert envelope["wake"]["url"] == wake_url
    server.shutdown()


def test_mission_wake_hook_via_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_SCHEDULER_HOOK_TOKEN", "tok")
    mock_tick = MagicMock(return_value={"ok": True, "runs": []})
    monkeypatch.setattr("agent_lab.mission.scheduler.scheduler_tick", mock_tick)

    r = client.post(
        "/api/hooks/mission-wake",
        headers={"X-Agent-Lab-Scheduler-Token": "tok"},
        json={},
    )
    assert r.status_code == 200
    assert r.json()["wake"] is True
    mock_tick.assert_called_once_with(force=True)


def test_run_live_soak_skipped_when_api_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_SOAK_SKIP_LAUNCHD", "1")
    report = run_live_tunnel_launchd_soak(api_base="http://127.0.0.1:1", skip_launchd=True)
    assert report["status"] == "skipped"


def test_launchd_agent_loaded_non_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent_lab.live_tunnel_launchd_soak.platform.system", lambda: "Linux")
    assert launchd_agent_loaded() is False


@pytest.mark.live
def test_live_tunnel_launchd_soak_real() -> None:
    import os

    if os.getenv("AGENT_LAB_RUN_LIVE", "").strip() not in {"1", "true", "yes"}:
        pytest.skip("set AGENT_LAB_RUN_LIVE=1 for live Tier E soak")
    report = run_live_tunnel_launchd_soak(skip_launchd=True)
    assert report["status"] in {"go", "skipped", "no_go"}
