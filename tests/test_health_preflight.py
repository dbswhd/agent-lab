"""Health preflight probes and room send gate."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from agent_lab.agent_preflight import (
    agent_preflight_row,
    agents_not_ready,
    format_codex_exec_error,
    validate_agents_for_run,
)


def test_format_codex_os_error_2():
    msg = format_codex_exec_error("Error: No such file or directory (os error 2)")
    assert "os error 2" in msg
    assert "CODEX_ROOM_WORKSPACE_WRITE" in msg


def test_agent_preflight_codex_cli_probe(monkeypatch):
    monkeypatch.setattr(
        "agent_lab.codex_cli.resolve_codex_bin",
        lambda: "/tmp/codex",
    )

    def fake_run(cmd, **kwargs):
        assert cmd[1] == "--version"
        return MagicMock(returncode=0, stdout="codex 1.2.3\n", stderr="")

    monkeypatch.setattr("agent_lab.agent_preflight.subprocess.run", fake_run)
    row = agent_preflight_row("codex", probe_bridge=False, probe_cli=True)
    assert row["ready"] is True


def test_agent_preflight_codex_missing_bin(monkeypatch):
    monkeypatch.setattr(
        "agent_lab.codex_cli.resolve_codex_bin",
        lambda: None,
    )
    row = agent_preflight_row("codex", probe_cli=False)
    assert row["ready"] is False
    assert row["reason"]


def test_validate_agents_for_run_raises(monkeypatch):
    monkeypatch.setattr(
        "agent_lab.agent_preflight.agent_preflight_row",
        lambda aid, **kw: {
            "id": aid,
            "ready": aid == "cursor",
            "reason": None if aid == "cursor" else "offline",
        },
    )
    with pytest.raises(ValueError, match="codex"):
        validate_agents_for_run(["cursor", "codex"])


def test_room_run_blocked_when_agent_not_ready(monkeypatch):
    from app.server.main import app

    monkeypatch.setattr(
        "app.server.main.agents_not_ready",
        lambda ids, **kw: [{"id": "codex", "ready": False, "reason": "codex CLI 없음"}],
    )
    client = TestClient(app)
    res = client.post(
        "/api/room/runs",
        data={
            "topic": "preflight gate test",
            "agents": json.dumps(["cursor", "codex"]),
            "mode": "discuss",
        },
    )
    assert res.status_code == 400
    body = res.json()
    assert body["detail"]["agents"][0]["id"] == "codex"


def test_release_room_run_lock_endpoint():
    from agent_lab.run_control import try_begin_run
    from app.server.main import app

    assert try_begin_run()
    client = TestClient(app)
    res = client.post("/api/room/runs/release-lock")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data.get("released") is True
    assert data.get("locked") is False


def test_health_probe_preflight_flag(monkeypatch):
    from agent_lab.agent_health import build_health_payload

    monkeypatch.setattr(
        "agent_lab.agent_preflight.build_agent_preflight",
        lambda **kw: [
            {"id": "cursor", "ready": True, "reason": None},
            {"id": "codex", "ready": False, "reason": "x"},
            {"id": "claude", "ready": True, "reason": None},
        ],
    )
    payload = build_health_payload(probe_preflight=True)
    assert payload["preflight"] is True
    assert len(payload["agents"]) == 3


def test_agents_not_ready_subset():
    bad = agents_not_ready(["unknown-agent"], probe_cli=False)
    assert bad  # unknown agent not ready


def test_cursor_bridge_preflight_keeps_fallback(monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent_lab.agent_health._cursor_sdk_installed",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent_lab.agent_preflight._bridge_bin_path",
        lambda: object(),
    )
    monkeypatch.setattr(
        "agent_lab.agent_health._check_cursor_bridge",
        lambda _ws: ("error", "Cursor bridge 연결 실패 (auto): dead"),
    )

    row = agent_preflight_row("cursor", probe_bridge=True, probe_cli=True)
    bad = agents_not_ready(["cursor"], probe_bridge=True, probe_cli=True)

    assert row["ready"] is False
    assert row["degraded"] is True
    assert "Codex/Claude" in row["fallback"]
    assert bad[0]["degraded"] is True
    assert "Codex/Claude" in bad[0]["fallback"]


def test_health_api_cursor_bridge_degraded_matches_fixture(monkeypatch):
    from app.server.main import app

    expected_path = (
        Path(__file__).resolve().parents[1]
        / "sessions"
        / "_regression"
        / "bridge_degraded_health"
        / "expected_health.json"
    )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    expected_cursor = next(row for row in expected["agents"] if row["id"] == "cursor")

    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent_lab.agent_health._cursor_sdk_installed",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent_lab.agent_preflight._bridge_bin_path",
        lambda: object(),
    )

    def fake_bridge_check(*_args, **_kwargs):
        return "error", expected_cursor["reason"]

    monkeypatch.setattr("agent_lab.agent_health._check_cursor_bridge", fake_bridge_check)

    client = TestClient(app)
    res = client.get("/api/health?probe_bridge=true&probe_preflight=true")
    assert res.status_code == 200
    cursor = next(row for row in res.json()["agents"] if row["id"] == "cursor")

    assert cursor["ready"] is False
    assert cursor["degraded"] is True
    assert cursor["failure_code"] == expected_cursor["failure_code"]
    assert cursor["fallback"] == expected_cursor["fallback"]
    assert cursor["remediation"] == expected_cursor["remediation"]
