"""GET /api/health/flags — AGENT_LAB_* discoverability."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from app.server.main import app

    return TestClient(app)


def test_health_flags_endpoint(client: TestClient):
    res = client.get("/api/health/flags")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["registry_count"] >= 60
    names = {row["name"] for row in body["flags"]}
    assert "AGENT_LAB_GOAL_LOOP" in names
    assert "AGENT_LAB_MOCK_AGENTS" in names
    assert "AGENT_LAB_MISSION_LOOP" in names


def test_health_flags_category_filter(client: TestClient):
    res = client.get("/api/health/flags?category=infra")
    assert res.status_code == 200
    body = res.json()
    assert body["category_filter"] == "infra"
    assert body["flags"]
    assert all(row["category"] == "infra" for row in body["flags"])


def test_health_flags_reflects_env(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_GOAL_LOOP", "1")
    res = client.get("/api/health/flags?category=feature")
    assert res.status_code == 200
    goal = next(row for row in res.json()["flags"] if row["name"] == "AGENT_LAB_GOAL_LOOP")
    assert goal["set"] is True
    assert goal["effective"] == "on"


def test_build_flags_payload_matches_cli():
    from agent_lab.runtime_flags import build_flags_payload

    payload = build_flags_payload(category="test")
    assert payload["category_filter"] == "test"
    assert any(row["name"] == "AGENT_LAB_MOCK_AGENTS" for row in payload["flags"])
