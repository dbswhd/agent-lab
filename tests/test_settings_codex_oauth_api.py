from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    cfg = tmp_path / ".agent-lab"
    cfg.mkdir()
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: cfg)
    monkeypatch.setattr(
        "agent_lab.codex_oauth.live_auth_path",
        lambda: tmp_path / ".codex" / "auth.json",
    )
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "auth.json").write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {}}),
        encoding="utf-8",
    )
    from app.server.main import app

    return TestClient(app)


def test_codex_oauth_probe_api(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.codex_oauth as co

    client.post(
        "/api/settings/codex-oauth/capture",
        json={"slot": "primary", "label": "메인"},
    )
    monkeypatch.setattr(co, "live_login_status", lambda: (True, "logged in"))

    res = client.post("/api/settings/codex-oauth/probe")
    assert res.status_code == 200
    body = res.json()
    assert body["probe_ok"] is True
    assert body["profiles"][0]["slot"] == "primary"


def test_codex_oauth_capture_api(client: TestClient) -> None:
    res = client.post(
        "/api/settings/codex-oauth/capture",
        json={"slot": "primary", "label": "메인"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["has_primary"] is True
    assert body["primary_label"] == "메인"
