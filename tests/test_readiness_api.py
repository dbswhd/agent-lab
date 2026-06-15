"""Readiness API (MB-9)."""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from app.server.main import app

    return TestClient(app)


def test_health_readiness_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.server.routers.health.build_readiness_payload",
        lambda **kw: {
            "verdict": "ready",
            "session_id": kw.get("session_id"),
            "checks": [{"id": "cursor_bridge", "ok": True, "next": None}],
            "next_actions": [],
            "agents": ["cursor", "codex", "claude"],
        },
    )
    res = client.get("/api/health/readiness?session_id=test-sess")
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == "ready"
    assert body["session_id"] == "test-sess"
    assert body["checks"]


def test_build_readiness_blocked_when_agent_fails(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "agent_lab.agent_preflight.agent_preflight_row",
        lambda aid, **kw: {
            "id": aid,
            "ready": aid == "cursor",
            "reason": None if aid == "cursor" else "offline",
            "remediation": ["Settings → fix"] if aid != "cursor" else [],
        },
    )
    from agent_lab.readiness import build_readiness_payload

    payload = build_readiness_payload(agent_ids=["cursor", "codex"])
    assert payload["verdict"] == "blocked"
    assert payload["next_actions"]
    codex_check = next(c for c in payload["checks"] if c["id"] == "codex_oauth")
    assert codex_check["ok"] is False


def test_build_readiness_ready_all_agents(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "agent_lab.agent_preflight.agent_preflight_row",
        lambda aid, **kw: {"id": aid, "ready": True},
    )
    from agent_lab.readiness import build_readiness_payload

    payload = build_readiness_payload()
    assert payload["verdict"] == "ready"
    assert payload["next_actions"] == []


def test_build_readiness_skips_probes_during_active_run(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[bool, bool]] = []

    def _row(aid, *, probe_bridge=True, probe_cli=True, **_kw):
        seen.append((probe_bridge, probe_cli))
        return {"id": aid, "ready": True}

    monkeypatch.setattr("agent_lab.agent_preflight.agent_preflight_row", _row)
    monkeypatch.setattr("agent_lab.run_control.room_run_in_progress", lambda: True)
    from agent_lab.readiness import build_readiness_payload

    payload = build_readiness_payload(agent_ids=["cursor", "codex"])
    assert payload["verdict"] == "ready"
    assert seen
    assert all(not b and not c for b, c in seen)
