"""Slack adapter signature + Events API coverage."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest
from fastapi.testclient import TestClient

from agent_lab.gateway.adapters import fan_out_gateway_notify
from agent_lab.gateway.adapters_slack import verify_slack_signature
from agent_lab.gateway.config import save_gateway_config
from app.server.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def gateway_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "gateway.toml"
    monkeypatch.setenv("AGENT_LAB_GATEWAY_CONFIG", str(path))
    return path


def test_verify_slack_signature_roundtrip() -> None:
    secret = "test-signing-secret"
    body = b'{"type":"event_callback"}'
    ts = str(int(time.time()))
    basestring = f"v0:{ts}:{body.decode()}"
    digest = hmac.new(secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()
    sig = f"v0={digest}"
    assert verify_slack_signature(secret, timestamp=ts, body=body, signature=sig) is True
    assert verify_slack_signature(secret, timestamp=ts, body=b"{}", signature=sig) is False


def test_slack_url_verification_challenge(client: TestClient, gateway_config) -> None:
    save_gateway_config({"slack": {"enabled": True, "allow_ingress_without_webhook": True}})
    r = client.post(
        "/api/gateway/slack/events",
        json={"type": "url_verification", "challenge": "challenge-token"},
    )
    assert r.status_code == 200
    assert r.json()["challenge"] == "challenge-token"


def test_slack_event_callback_ignores_bot_message(client: TestClient, gateway_config) -> None:
    save_gateway_config({"slack": {"enabled": True, "allow_ingress_without_webhook": True}})
    r = client.post(
        "/api/gateway/slack/events",
        json={
            "type": "event_callback",
            "event": {"type": "message", "bot_id": "B1", "text": "hello"},
        },
    )
    assert r.status_code == 200
    assert r.json()["skipped"] is True


def test_slack_invalid_signature_rejected(client: TestClient, gateway_config) -> None:
    save_gateway_config(
        {
            "slack": {
                "enabled": True,
                "signing_secret": "secret",
                "allow_ingress_without_webhook": True,
            },
        }
    )
    r = client.post(
        "/api/gateway/slack/events",
        json={"type": "event_callback", "event": {"text": "/status"}},
        headers={
            "X-Slack-Request-Timestamp": str(int(time.time())),
            "X-Slack-Signature": "v0=deadbeef",
        },
    )
    assert r.status_code == 401


def test_slack_notify_merge_ready(gateway_config) -> None:
    posted: list[bytes] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            posted.append(self.rfile.read(length))
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
            "adapters": {"enabled": ["slack"]},
            "slack": {
                "enabled": True,
                "webhook_url": f"http://127.0.0.1:{port}/hook",
            },
        }
    )
    result = fan_out_gateway_notify(
        "merge_ready",
        {"session_id": "s1", "execution_id": "ex-1"},
    )
    assert any(row.get("adapter") == "slack" and row.get("ok") is True for row in result["adapters"])
    assert posted
    payload = json.loads(posted[0].decode())
    assert "merge ready" in payload["text"]
    server.shutdown()
