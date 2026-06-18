"""G005 — slash command surface (6 commands), masked output, write path, settings gate."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import agent_lab.app_config as app_config

    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    return tmp_path


def test_parse_command() -> None:
    from agent_lab.slash_commands import is_slash_command, parse_command

    assert parse_command("/login kimi sk-1") == ("login", ["kimi", "sk-1"])
    assert parse_command("not a command") is None
    assert parse_command("/bogus") == ("bogus", [])
    assert is_slash_command("/usage") is True
    assert is_slash_command("/bogus") is False
    assert is_slash_command("hello") is False


def test_all_six_commands_dispatch(cfg: Path) -> None:
    from agent_lab.slash_commands import SLASH_COMMANDS, dispatch

    assert set(SLASH_COMMANDS) == {"login", "logout", "accounts", "model", "usage", "agents"}
    for cmd in ("model", "usage", "agents"):
        res = dispatch(f"/{cmd}")
        assert res["ok"] is True and res["command"] == cmd


def test_login_api_provider_masked(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/login kimi sk-supersecret-1234")
    assert res["ok"] is True and res["provider"] == "kimi"
    # secret never echoed in clear
    masked = res["accounts"][0]["masked"]
    assert masked is not None and "sk-supersecret-1234" not in str(res)
    assert masked.endswith("1234")


def test_login_oauth_no_secret_storage(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/login codex")
    assert res["ok"] is True and res["auth_kind"] == "oauth"
    assert "note" in res  # CLI OAuth flow, profile-referenced not stored


def test_accounts_add_list_remove_masked(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    add = dispatch("/accounts kimi add primary sk-abcd1234")
    assert add["ok"] is True and add["added"] == "primary"
    listed = dispatch("/accounts kimi list")
    assert listed["accounts"][0]["label"] == "primary"
    assert "sk-abcd1234" not in str(listed) and listed["accounts"][0]["masked"].endswith("1234")
    removed = dispatch("/accounts kimi remove primary")
    assert removed["accounts"] == []


def test_accounts_write_path_persists(cfg: Path) -> None:
    from agent_lab import credential_store as cs
    from agent_lab.slash_commands import dispatch

    dispatch("/accounts kimi add a1 sk-1")
    assert [a["label"] for a in cs.get_provider_accounts("kimi")] == ["a1"]


def test_logout_clears(cfg: Path) -> None:
    from agent_lab import credential_store as cs
    from agent_lab.slash_commands import dispatch

    dispatch("/accounts kimi add a1 sk-1")
    res = dispatch("/logout kimi")
    assert res["cleared"] is True
    assert cs.get_provider_accounts("kimi") == []


def test_model_view_and_set(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.slash_commands import dispatch

    monkeypatch.delenv("AGENT_LAB_ROOM_MODELS", raising=False)
    view = dispatch("/model")
    assert view["composition"] == ["cursor", "codex", "claude"]
    upd = dispatch("/model cursor,kimi,claude")
    assert upd["updated"] is True and upd["composition"] == ["cursor", "kimi", "claude"]


def test_usage_reports_cooldown(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    dispatch("/accounts kimi add a1 sk-1")
    res = dispatch("/usage kimi")
    assert res["ok"] is True
    row = next(r for r in res["rows"] if r["label"] == "a1")
    assert row["cooldown_active"] is False and row["usage_exposing"] is True


def test_agents_reports_roster_and_roles(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/agents")
    assert res["roster"] == ["cursor", "codex", "claude"]
    assert res["roles"]["cursor"] == "propose"


def test_settings_put_readonly_when_dynamic(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.server.main import app

    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "1")
    client = TestClient(app)
    res = client.put("/api/settings/credentials", json={"cursor": {"primary": "sk-x"}})
    assert res.status_code == 200
    body = res.json()
    assert body.get("saved") is False and body.get("read_only") is True


def test_settings_put_writes_when_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    import agent_lab.app_config as app_config
    from app.server.main import app

    monkeypatch.delenv("AGENT_LAB_DYNAMIC_ROOM", raising=False)
    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    client = TestClient(app)
    res = client.put("/api/settings/credentials", json={"cursor": {"primary": "sk-off"}})
    assert res.status_code == 200
    assert res.json().get("saved") is True  # OFF-parity: legacy write path intact
