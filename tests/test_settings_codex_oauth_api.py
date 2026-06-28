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
        "agent_lab.codex.oauth.live_auth_path",
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
    import agent_lab.codex.oauth as co

    capture = client.post(
        "/api/settings/codex-oauth/capture",
        json={"slot": "primary", "label": "메인"},
    )
    assert capture.json()["read_only"] is True
    monkeypatch.setattr(co, "live_login_status", lambda: (True, "logged in"))

    res = client.post("/api/settings/codex-oauth/probe")
    assert res.status_code == 200
    body = res.json()
    assert body["probe_ok"] is False
    assert body["profiles"] == []


def test_codex_oauth_capture_api_is_readonly(client: TestClient) -> None:
    before = client.get("/api/settings/codex-oauth").json()
    res = client.post(
        "/api/settings/codex-oauth/capture",
        json={"slot": "primary", "label": "메인"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["read_only"] is True
    for field in ("has_primary", "has_fallback", "primary_label", "fallback_label"):
        assert body[field] == before[field]
