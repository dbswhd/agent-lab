"""Agent health panel data."""

from __future__ import annotations

from agent_lab.agent.health import agent_health_row, build_agent_health, reconnect_cursor_bridge


def test_agent_health_codex_when_bin_missing(monkeypatch):
    monkeypatch.setattr(
        "agent_lab.codex_cli.resolve_codex_bin",
        lambda: None,
    )
    row = agent_health_row("codex")
    assert row["configured"] is False
    assert row["ready"] is False
    assert row["hint"]


def test_agent_health_cursor_without_key(monkeypatch):
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr(
        "agent_lab.agent.health._cursor_sdk_installed",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent_lab.credential_store.provider_has_credentials",
        lambda _provider: False,
    )
    row = agent_health_row("cursor", probe_bridge=False)
    assert row["configured"] is False
    assert row["bridge"] == "n/a" or row["bridge"] == "unknown"


def test_build_agent_health_three_agents():
    rows = build_agent_health(probe_bridge=False)
    assert [r["id"] for r in rows] == [
        "cursor",
        "codex",
        "claude",
        "kimi_work",
        "kimi",
        "local",
    ]


def test_reconnect_cursor_bridge_invalidates(monkeypatch):
    calls: list[str] = []

    def fake_invalidate(workspace: str) -> None:
        calls.append(workspace)

    monkeypatch.setattr(
        "agent_lab.cursor_bridge.invalidate_workspace",
        fake_invalidate,
    )
    monkeypatch.setattr(
        "agent_lab.agent.health._check_cursor_bridge",
        lambda _ws, retries=3: ("ok", None),
    )
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent_lab.agent.health._cursor_sdk_installed",
        lambda: True,
    )
    out = reconnect_cursor_bridge(workspace="/tmp/ws")
    assert out["ok"] is True
    assert out["bridge"] == "ok"
    assert calls == ["/tmp/ws"]


def test_agent_health_cursor_bridge_failure_has_fallback(monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent_lab.agent.health._cursor_sdk_installed",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent_lab.agent.health._check_cursor_bridge",
        lambda _ws, retries=3: ("error", "Cursor bridge 연결 실패 (external): dead"),
    )

    row = agent_health_row("cursor", probe_bridge=True)

    assert row["ready"] is False
    assert row["degraded"] is True
    assert row["failure_code"] == "cursor_bridge_unavailable"
    assert "Codex/Claude" in row["fallback"]


def test_reconnect_cursor_bridge_failure_has_fallback(monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(
        "agent_lab.agent.health._cursor_sdk_installed",
        lambda: True,
    )
    monkeypatch.setattr("agent_lab.cursor_bridge.invalidate_workspace", lambda _ws: None)
    monkeypatch.setattr(
        "agent_lab.agent.health._check_cursor_bridge",
        lambda _ws, retries=3: ("error", "bridge ping 실패"),
    )

    out = reconnect_cursor_bridge(workspace="/tmp/ws")

    assert out["ok"] is False
    assert out["agent"]["degraded"] is True
    assert "Codex/Claude" in out["agent"]["fallback"]
