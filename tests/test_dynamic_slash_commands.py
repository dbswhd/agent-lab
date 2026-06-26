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


@pytest.fixture(autouse=True)
def _restore_room_models() -> object:
    """/model writes AGENT_LAB_ROOM_MODELS to os.environ directly; isolate it."""
    import os

    prev = os.environ.get("AGENT_LAB_ROOM_MODELS")
    yield
    if prev is None:
        os.environ.pop("AGENT_LAB_ROOM_MODELS", None)
    else:
        os.environ["AGENT_LAB_ROOM_MODELS"] = prev


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

    # Dynamic-room commands (pipeline handles pipeline/clarify/plan are a separate category).
    assert {"login", "logout", "accounts", "model", "usage", "agents"}.issubset(set(SLASH_COMMANDS))
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


def test_logout_staged_provider_choices(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/logout")
    assert res["ok"] is True and res["command"] == "logout"
    assert res["stage"] == "provider"
    assert "로그아웃할 공급자 선택" in res["prompt"]
    values = {opt["value"] for opt in res["choices"]["options"]}
    assert values >= {"cursor", "claude", "codex", "kimi"}
    assert "local" not in values


def test_logout_unknown_provider(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/logout bogus")
    assert res["ok"] is False
    assert "unknown provider" in res["error"]


def test_logout_local_rejected(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/logout local")
    assert res["ok"] is False
    assert "local" in res["error"].lower()


def test_logout_oauth_provider_starts_cli_flow(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/logout claude")
    assert res["ok"] is True
    assert res["provider"] == "claude"
    assert res["auth_kind"] == "oauth"
    assert "CLI 로그아웃" in res["note"]


def test_logout_cursor_clears_api_accounts_then_oauth(cfg: Path) -> None:
    from agent_lab import credential_store as cs
    from agent_lab.slash_commands import dispatch

    dispatch("/accounts cursor add a1 sk-1")
    data = cs.load_credentials(create_default=False)
    data["cursor"]["primary"] = "crsr_test_key"
    cs.save_credentials(data)
    res = dispatch("/logout cursor")
    assert res["ok"] is True
    assert res["provider"] == "cursor"
    assert res["auth_kind"] == "oauth"
    assert res["cleared"] is True
    assert res["cleared_credentials"] is True
    assert cs.get_provider_accounts("cursor") == []
    after = cs.load_credentials(create_default=False)
    assert not str(after["cursor"].get("primary") or "").strip()


def test_login_cursor_without_key_starts_oauth(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/login cursor")
    assert res["ok"] is True
    assert res["provider"] == "cursor"
    assert res["auth_kind"] == "oauth"


def test_model_view_and_set(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.slash_commands import dispatch

    monkeypatch.delenv("AGENT_LAB_ROOM_MODELS", raising=False)
    view = dispatch("/model")
    assert view["composition"] == ["cursor", "codex", "claude"]
    staged = dispatch("/model cursor,kimi,claude")
    assert staged["stage"] == "persist"
    assert staged["composition"] == ["cursor", "kimi", "claude"]
    upd = dispatch("/model cursor,kimi,claude session")
    assert upd["updated"] is True and upd["composition"] == ["cursor", "kimi", "claude"]
    assert upd["scope"] == "session"


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


def test_settings_put_remains_readonly_when_dynamic_room_is_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fastapi.testclient import TestClient

    import agent_lab.app_config as app_config
    from app.server.main import app

    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "0")
    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    client = TestClient(app)
    before = client.get("/api/settings/credentials").json()
    res = client.put("/api/settings/credentials", json={"cursor": {"primary": "sk-off"}})
    assert res.status_code == 200
    body = res.json()
    assert body.get("saved") is False
    assert body.get("read_only") is True
    cursor = next(row for row in body["agents"] if row["id"] == "cursor")
    cursor_before = next(row for row in before["agents"] if row["id"] == "cursor")
    assert cursor == cursor_before


# --- Composer integration: command_registry catalog + dispatch (option A) ---


def test_command_registry_gates_dynamic_room(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The 6 dynamic-room commands appear in the composer catalog only when on."""
    from agent_lab.command_registry import list_commands

    account_commands = {"login", "logout", "accounts"}
    room_commands = {"model", "usage", "agents"}

    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "0")
    off_ids = {c["id"] for c in list_commands(cfg, workspace=cfg)["commands"]}
    assert account_commands <= off_ids
    assert room_commands.isdisjoint(off_ids)

    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "1")
    on = list_commands(cfg, workspace=cfg)["commands"]
    on_ids = {c["id"] for c in on}
    assert account_commands | room_commands <= on_ids
    for row in on:
        if row["id"] in account_commands | room_commands:
            assert row["slash"] == f"/{row['id']}"
            assert row["kind"] == "server"
            assert row["enabled"] is True
            assert row["handler"] == f"dynamic_room:{row['id']}"


def test_execute_command_dispatches_dynamic_room(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """execute_command delegates to slash_commands.dispatch with composer-renderable text."""
    from agent_lab.command_registry import execute_command, invoke_tool

    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "1")
    # _model writes AGENT_LAB_ROOM_MODELS directly; record it so teardown clears it.
    monkeypatch.setenv("AGENT_LAB_ROOM_MODELS", "")

    res = execute_command(cfg, "agents", workspace=cfg)
    assert res["ok"] is True and res["kind"] == "server"
    # /agents without args now shows a non-expert picker prompt below the composer.
    assert res["text"] == "현재 Room 로스터" or res["text"].startswith("/agents roster:")
    assert res["result"].get("stage") == "roster"
    # roster is dynamically resolved when dynamic room is on; just assert wiring.
    roster = res["result"]["roster"]
    assert isinstance(roster, list) and roster
    assert set(res["result"]["roles"]) == set(roster)

    setm = execute_command(cfg, "model", args="kimi,local", workspace=cfg)
    assert setm["ok"] is True and "kimi" in setm["text"]

    # invoke_tool envelope stays ok for the server-kind dynamic command
    tr = invoke_tool(cfg, "usage", workspace=cfg)
    assert tr.ok is True and tr.kind == "server"


def test_execute_command_dynamic_room_error_surfaces_detail(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.command_registry import execute_command

    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "1")
    # /login with no args now returns the auth-method picker (ok); use a real error.
    res = execute_command(cfg, "login", args="bogus", workspace=cfg)  # unknown provider
    assert res["ok"] is False
    assert "unknown provider" in res["detail"]
    assert "result" not in res  # gate-failure shape → endpoint 409 with detail


def test_execute_command_dynamic_room_blocked_when_off(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.command_registry import execute_command

    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "0")
    res = execute_command(cfg, "usage", workspace=cfg)
    assert res["ok"] is False
    assert "unknown command" in (res.get("detail") or "")


def test_account_commands_remain_available_when_dynamic_room_is_off(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.command_registry import execute_command

    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "0")
    res = execute_command(cfg, "accounts", args="kimi list", workspace=cfg)
    assert res["ok"] is True


# --- Phase 3: staged /login picker (auth method -> provider -> key) ---


def test_login_stage_auth_method_choices(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/login")
    assert res["ok"] is True and res["stage"] == "auth_method"
    values = [o["value"] for o in res["choices"]["options"]]
    assert values == ["oauth", "api"]  # local needs no login


def test_login_stage_provider_choices_by_method(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    oauth = dispatch("/login oauth")["choices"]
    assert oauth["kind"] == "provider" and oauth["method"] == "oauth"
    assert {o["value"] for o in oauth["options"]} == {"claude", "codex", "cursor"}

    api = dispatch("/login api")["choices"]
    assert {o["value"] for o in api["options"]} == {"cursor", "kimi"}


def test_login_stage_api_prompts_for_secret_then_stores(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    prompt = dispatch("/login api kimi")
    assert prompt["stage"] == "secret"
    assert prompt["input"]["prefill"] == "/login api kimi "

    stored = dispatch("/login api kimi sk-staged-7777")
    assert stored["provider"] == "kimi"
    assert stored["accounts"][0]["masked"].endswith("7777")
    assert "sk-staged-7777" not in str(stored)


def test_login_stage_oauth_provider_returns_cli_note(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/login oauth claude")
    assert res["auth_kind"] == "oauth" and "note" in res


def test_login_legacy_positional_still_works(cfg: Path) -> None:
    from agent_lab.slash_commands import dispatch

    assert dispatch("/login codex")["auth_kind"] == "oauth"
    assert dispatch("/login kimi sk-legacy-2222")["accounts"][-1]["masked"].endswith("2222")
