"""Health preflight probes and room send gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.agent.preflight import (
    agent_preflight_row,
    agents_not_ready,
    format_codex_exec_error,
    validate_agents_for_run,
)


@pytest.fixture(autouse=True)
def _isolate_room_models_for_health(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import agent_lab.app_config as app_config

    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    monkeypatch.delenv("AGENT_LAB_ROOM_MODELS", raising=False)
    yield
    import os

    os.environ.pop("AGENT_LAB_ROOM_MODELS", None)


def test_format_codex_os_error_2():
    msg = format_codex_exec_error("Error: No such file or directory (os error 2)")
    assert "os error 2" in msg
    assert "CODEX_ROOM_WORKSPACE_WRITE" in msg


def test_agent_preflight_claude_auth_failure(monkeypatch):
    monkeypatch.setenv("CLAUDE_SKIP_AUTH_PROBE", "0")
    monkeypatch.setattr(
        "agent_lab.claude.cli.resolve_claude_bin",
        lambda: "/tmp/claude",
    )
    monkeypatch.setattr(
        "agent_lab.claude.cli.claude_auth_logged_in",
        lambda **kw: (False, "401 Invalid authentication credentials"),
    )
    monkeypatch.setattr(
        "agent_lab.claude.cli.probe_auth",
        lambda **kw: (False, "401 Invalid authentication credentials"),
    )
    monkeypatch.setattr(
        "agent_lab.agent.preflight._probe_cli_version",
        lambda *_args, **_kwargs: (True, "2.1.147"),
    )
    row = agent_preflight_row("claude", probe_bridge=False, probe_cli=True)
    assert row["ready"] is False
    assert row["failure_code"] == "claude_auth_failed"
    assert row["remediation"]
    assert "claude login" in " ".join(row["remediation"]).lower()


def test_agent_preflight_codex_cli_probe(monkeypatch):
    monkeypatch.setattr(
        "agent_lab.codex.cli.resolve_codex_bin",
        lambda: "/tmp/codex",
    )
    monkeypatch.setattr(
        "agent_lab.codex.oauth.codex_oauth_ready",
        lambda: (True, "logged in"),
    )
    monkeypatch.setattr(
        "agent_lab.agent.preflight._probe_cli_version",
        lambda *_args, **_kwargs: (True, "codex 1.2.3"),
    )
    monkeypatch.setattr(
        "agent_lab.codex.oauth.probe_captured_profiles",
        lambda: [],
    )
    row = agent_preflight_row("codex", probe_bridge=False, probe_cli=True)
    assert row["ready"] is True


def test_agent_preflight_codex_missing_bin(monkeypatch):
    monkeypatch.setattr(
        "agent_lab.codex.cli.resolve_codex_bin",
        lambda: None,
    )
    row = agent_preflight_row("codex", probe_cli=False)
    assert row["ready"] is False
    assert row["reason"]


def test_validate_agents_for_run_raises(monkeypatch):
    monkeypatch.setattr(
        "agent_lab.agent.preflight.agent_preflight_row",
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
        "agent_lab.agent.preflight.agents_not_ready",
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
    from agent_lab.run.control import try_begin_run
    from app.server.main import app

    assert try_begin_run()
    client = TestClient(app)
    res = client.post("/api/room/runs/release-lock")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data.get("released") is True
    assert data.get("locked") is False


def test_reconnect_claude_auth_invalidates_cache(monkeypatch):
    from agent_lab.agent.health import reconnect_claude_auth

    invalidated: list[str] = []

    def fake_invalidate() -> None:
        invalidated.append("yes")

    monkeypatch.setattr(
        "agent_lab.claude.cli.invalidate_claude_auth_cache",
        fake_invalidate,
    )
    monkeypatch.setattr(
        "agent_lab.claude.cli.resolve_claude_bin",
        lambda: "/tmp/claude",
    )
    monkeypatch.setattr(
        "agent_lab.claude.cli.claude_auth_logged_in",
        lambda **kw: (True, None) if not kw.get("use_cache", True) else (False, "stale"),
    )
    monkeypatch.setattr(
        "agent_lab.claude.cli.probe_auth",
        lambda **kw: (True, None),
    )

    out = reconnect_claude_auth()

    assert invalidated == ["yes"]
    assert out["ok"] is True
    assert out["auth_ok"] is True
    assert out["probe_ok"] is True
    assert out["agent"]["ready"] is True


def test_reconnect_claude_auth_failure_has_remediation(monkeypatch):
    from agent_lab.agent.health import reconnect_claude_auth

    monkeypatch.setattr("agent_lab.claude.cli.invalidate_claude_auth_cache", lambda: None)
    monkeypatch.setattr(
        "agent_lab.claude.cli.resolve_claude_bin",
        lambda: "/tmp/claude",
    )
    monkeypatch.setattr(
        "agent_lab.claude.cli.claude_auth_logged_in",
        lambda **kw: (False, "Not logged in — run: claude auth login"),
    )

    out = reconnect_claude_auth()

    assert out["ok"] is False
    assert out["auth_ok"] is False
    assert out["probe_ok"] is False
    assert out["agent"]["failure_code"] == "claude_auth_failed"
    assert out["remediation"]


def test_health_probe_preflight_flag(monkeypatch):
    from agent_lab.agent.health import build_health_payload

    monkeypatch.setattr(
        "agent_lab.agent.preflight.build_agent_preflight",
        lambda **kw: [
            {"id": "cursor", "ready": True, "reason": None},
            {"id": "codex", "ready": False, "reason": "x"},
            {"id": "claude", "ready": True, "reason": None},
        ],
    )
    payload = build_health_payload(probe_preflight=True)
    assert payload["preflight"] is True
    assert payload["room_composition"] == ["cursor", "codex", "claude"]
    assert len(payload["agents"]) == 3
    cursor = next(row for row in payload["agents"] if row["id"] == "cursor")
    assert cursor["team_ready"] is True
    assert cursor["loop_ready"] is True


@pytest.mark.integration
def test_health_payload_includes_model_readiness() -> None:
    from agent_lab.agent.health import build_health_payload

    payload = build_health_payload()
    rows = {row["id"]: row for row in payload["agents"]}

    assert payload["room_composition"] == ["cursor", "codex", "claude"]
    assert set(rows) == {"cursor", "codex", "claude"}
    assert len(payload["agents_all"]) >= len(payload["agents"])
    assert rows["cursor"]["team_ready"] is True
    assert rows["cursor"]["loop_ready"] is True
    assert rows["cursor"]["model_provider"] == "local"
    assert rows["cursor"]["loop_blockers"] == []
    assert rows["cursor"]["model_cost_tier"] == "low"
    assert rows["cursor"]["loop_cost_blocked"] is False
    assert rows["codex"]["loop_ready"] is True


def test_health_payload_sessions_dir_uses_active_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.session as session_mod
    import agent_lab.session.paths as paths_mod
    from agent_lab.agent.health import build_health_payload

    expected = tmp_path / "sessions"
    expected.mkdir()
    # Clear every module-level cache — CI sets AGENT_LAB_ROOT and may have
    # bootstrapped app.server.deps.SESSIONS_DIR to the workspace sessions root.
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", None)
    monkeypatch.setattr(paths_mod, "SESSIONS_DIR", None)
    try:
        import app.server.deps as deps_mod

        monkeypatch.setattr(deps_mod, "SESSIONS_DIR", None)
    except Exception:
        pass
    monkeypatch.setenv("AGENT_LAB_SESSIONS_DIR", str(expected))
    monkeypatch.delenv("AGENT_LAB_ROOT", raising=False)

    payload = build_health_payload()
    assert payload["sessions_dir"] == str(expected)


def test_health_payload_filters_to_kimi_work_composition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.app_config as app_config
    from agent_lab.room import models_config as rmc
    from agent_lab.agent.health import build_health_payload

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr(app_config, "config_dir", lambda: cfg)
    rmc.persist_default_room_models(["kimi_work"])

    payload = build_health_payload()
    assert payload["room_composition"] == ["kimi_work"]
    assert [row["id"] for row in payload["agents"]] == ["kimi_work"]
    assert len(payload["agents_all"]) >= 1


def test_agents_not_ready_subset():
    bad = agents_not_ready(["unknown-agent"], probe_cli=False)
    assert bad  # unknown agent not ready


def test_cursor_bridge_preflight_keeps_fallback(monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent_lab.agent.health._cursor_sdk_installed",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent_lab.agent.preflight._bridge_bin_path",
        lambda: object(),
    )
    monkeypatch.setattr(
        "agent_lab.agent.health._check_cursor_bridge",
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
        "agent_lab.agent.health._cursor_sdk_installed",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent_lab.agent.preflight._bridge_bin_path",
        lambda: object(),
    )

    def fake_bridge_check(*_args, **_kwargs):
        return "error", expected_cursor["reason"]

    monkeypatch.setattr("agent_lab.agent.health._check_cursor_bridge", fake_bridge_check)

    client = TestClient(app)
    res = client.get("/api/health?probe_bridge=true&probe_preflight=true")
    assert res.status_code == 200
    cursor = next(row for row in res.json()["agents"] if row["id"] == "cursor")

    assert cursor["ready"] is False
    assert cursor["degraded"] is True
    assert cursor["failure_code"] == expected_cursor["failure_code"]
    assert cursor["fallback"] == expected_cursor["fallback"]
    assert cursor["remediation"] == expected_cursor["remediation"]
