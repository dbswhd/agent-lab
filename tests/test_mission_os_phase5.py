"""Mission OS Phase 5 — Gateway E plugins + hybrid relay."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest
from fastapi.testclient import TestClient

from agent_lab.gateway.adapters import fan_out_gateway_notify, public_adapters_payload
from agent_lab.gateway.config import save_gateway_config
from agent_lab.gateway.hybrid_relay import daemon_online, maybe_deliver_hybrid_relay
from agent_lab.human_inbox import create_inbox_item
from app.server.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    folder = tmp_path / "gw5-sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("gw5\n", encoding="utf-8")
    (folder / "run.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    return folder


@pytest.fixture
def gateway_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "gateway.toml"
    monkeypatch.setenv("AGENT_LAB_GATEWAY_CONFIG", str(path))
    save_gateway_config(
        {
            "adapters": {"enabled": ["telegram", "webhook_inbound", "cli", "discord", "slack"]},
            "discord": {"allow_ingress_without_webhook": True},
            "slack": {"enabled": True, "webhook_url": "https://hooks.slack.com/services/test"},
        }
    )
    return path


def test_adapter_registry_lists_five(gateway_config: Path) -> None:
    payload = public_adapters_payload()
    ids = {row["id"] for row in payload["adapters"]}
    assert ids == {"cli", "discord", "slack", "telegram", "webhook_inbound"}


def test_cli_ingress_status(client: TestClient, session_folder: Path, gateway_config: Path) -> None:
    r = client.post(
        "/api/gateway/cli",
        json={"text": "/status", "session_id": session_folder.name},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "reply" in r.json()


def test_webhook_ingress_via_adapter(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_config: Path,
) -> None:
    routes = tmp_path / "routes.toml"
    routes.write_text(
        """
[[route]]
match = { channel = "webhook", hook_id = "github-ci" }
session_id = "ci-triage"
gate_profile = "assistant"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_ROUTES_CONFIG", str(routes))
    r = client.post("/api/hooks/github-ci", json={"text": "build failed"})
    assert r.status_code == 200
    assert r.json()["route"]["session_id"] == "ci-triage"


def test_hybrid_relay_when_daemon_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_config: Path,
) -> None:
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

    relay_url = f"http://127.0.0.1:{port}/relay"
    save_gateway_config(
        {
            "hybrid": {
                "enabled": True,
                "relay_url": relay_url,
                "relay_when": "daemon_offline",
            },
        }
    )
    monkeypatch.setenv("AGENT_LAB_DAEMON_STATE", str(tmp_path / "missing_daemon.json"))
    assert daemon_online() is False

    result = maybe_deliver_hybrid_relay("inbox_pending", {"session_id": "s1"})
    assert result.get("ok") is True
    assert received
    body = json.loads(received[0].decode("utf-8"))
    assert body["event"] == "inbox_pending"
    server.shutdown()


def test_fan_out_calls_hybrid_when_offline(
    session_folder: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_config: Path,
) -> None:
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

    save_gateway_config(
        {
            "hybrid": {
                "enabled": True,
                "relay_url": f"http://127.0.0.1:{port}/relay",
            },
            "telegram": {"enabled": False},
        }
    )
    monkeypatch.setenv("AGENT_LAB_DAEMON_STATE", str(tmp_path / "missing_daemon.json"))

    item = {
        "id": "inbox-x",
        "kind": "question",
        "prompt": "Pick?",
    }
    fan_out_gateway_notify(
        "inbox_pending",
        {"session_id": session_folder.name, "item": item},
    )
    assert received
    server.shutdown()


def test_inbox_create_triggers_fan_out(
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_config: Path,
) -> None:
    calls: list[str] = []

    def _fan_out(event, payload, **kwargs):
        calls.append(event)
        return {"ok": True, "event": event}

    monkeypatch.setattr("agent_lab.gateway.adapters.fan_out_gateway_notify", _fan_out)
    create_inbox_item(
        session_folder,
        kind="question",
        source="manual",
        prompt="Hello?",
        options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
    )
    assert "inbox_pending" in calls


def test_gateway_adapters_api(client: TestClient, gateway_config: Path) -> None:
    r = client.get("/api/gateway/adapters")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["adapters"]) >= 5


def test_slack_ingress_status(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gateway_config: Path,
) -> None:
    routes = tmp_path / "routes.toml"
    routes.write_text(
        """
[[route]]
match = { channel = "slack", prefix = "/ops" }
session_id = "slack-sess"
gate_profile = "assistant"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_ROUTES_CONFIG", str(routes))
    save_gateway_config(
        {
            "slack": {
                "enabled": True,
                "webhook_url": "",
                "bot_token": "xoxb-test",
            },
        }
    )
    r = client.post(
        "/api/gateway/slack/events",
        json={"content": "/ops/status", "channel_id": "C1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("route", {}).get("channel") == "slack"
    assert body.get("route", {}).get("session_id") == "slack-sess"
