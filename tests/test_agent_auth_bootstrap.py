"""Startup auth bootstrap tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def agent_lab_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / ".agent-lab"
    cfg.mkdir()
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: cfg)
    monkeypatch.setenv("CURSOR_API_KEY", "crsr_test_key_12345")
    return cfg


def test_persist_cursor_api_key_from_env(agent_lab_home: Path) -> None:
    from agent_lab.agent.auth_bootstrap import persist_cursor_api_key_from_env
    from agent_lab.credential_store import load_credentials

    assert persist_cursor_api_key_from_env() is True
    data = load_credentials()
    assert data["cursor"]["primary"] == "crsr_test_key_12345"
    dotenv = (agent_lab_home / ".env").read_text(encoding="utf-8")
    assert "CURSOR_API_KEY=crsr_test_key_12345" in dotenv


def test_sync_codex_applies_primary_when_live_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.codex import oauth as co
    from agent_lab.agent.auth_bootstrap import sync_codex_oauth_on_startup

    cfg = tmp_path / ".agent-lab"
    cfg.mkdir()
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: cfg)
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    live = codex_dir / "auth.json"
    live.write_text(json.dumps({"auth_mode": "chatgpt", "tokens": {"access": "stale"}}), encoding="utf-8")
    monkeypatch.setattr(co, "live_auth_path", lambda: live)

    (cfg / "codex-oauth" / "primary").mkdir(parents=True)
    (cfg / "codex-oauth" / "primary" / "auth.json").write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {"access": "fresh"}}),
        encoding="utf-8",
    )
    (cfg / "codex-oauth" / "meta.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        co,
        "live_login_status",
        lambda: (False, "not logged in"),
    )

    out = sync_codex_oauth_on_startup()
    assert out["applied_primary"] is True
    data = json.loads(live.read_text(encoding="utf-8"))
    assert data["tokens"]["access"] == "fresh"


def test_sync_codex_recaptures_from_fresher_live_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A re-login (newer live token, same account) must refresh the snapshot,
    not be stomped by the stale (possibly revoked) captured profile."""
    from agent_lab.codex import oauth as co
    from agent_lab.agent.auth_bootstrap import sync_codex_oauth_on_startup

    cfg = tmp_path / ".agent-lab"
    cfg.mkdir()
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: cfg)
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    live = codex_dir / "auth.json"
    monkeypatch.setattr(co, "live_auth_path", lambda: live)

    def payload(last_refresh: str, token: str) -> str:
        return json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {"account_id": "acct-1", "refresh_token": token},
                "last_refresh": last_refresh,
            }
        )

    (cfg / "codex-oauth" / "primary").mkdir(parents=True)
    (cfg / "codex-oauth" / "primary" / "auth.json").write_text(
        payload("2026-06-19T10:00:00Z", "revoked"), encoding="utf-8"
    )
    live.write_text(payload("2026-07-03T09:00:00Z", "fresh"), encoding="utf-8")
    monkeypatch.setattr(co, "live_login_status", lambda: (True, "logged in"))

    out = sync_codex_oauth_on_startup()
    assert out["synced_primary_from_live"] is True
    assert out["applied_primary"] is False
    live_data = json.loads(live.read_text(encoding="utf-8"))
    assert live_data["tokens"]["refresh_token"] == "fresh"
    snap = json.loads((cfg / "codex-oauth" / "primary" / "auth.json").read_text(encoding="utf-8"))
    assert snap["tokens"]["refresh_token"] == "fresh"


def test_bootstrap_skipped_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.agent.auth_bootstrap import bootstrap_room_auth_on_startup

    monkeypatch.setenv("AGENT_LAB_SKIP_AUTH_BOOTSTRAP", "1")
    assert bootstrap_room_auth_on_startup() == {"skipped": True}
