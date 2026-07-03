from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.codex import oauth as co
from agent_lab.credential_store import get_credential_chain, load_credentials, save_credentials


@pytest.fixture
def oauth_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / ".agent-lab"
    cfg.mkdir()
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: cfg)
    monkeypatch.setattr(co, "live_auth_path", lambda: tmp_path / ".codex" / "auth.json")
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "auth.json").write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {"access": "a"}}),
        encoding="utf-8",
    )
    return tmp_path


def test_capture_and_apply_profile(oauth_home: Path) -> None:
    result = co.capture_profile("primary", label="Work")
    assert result["ok"] is True
    assert co.profile_exists("primary")
    live = co.live_auth_path()
    live.write_text('{"stale": true}', encoding="utf-8")
    co.apply_profile("primary")
    data = json.loads(live.read_text(encoding="utf-8"))
    assert data.get("auth_mode") == "chatgpt"


def test_oauth_chain_two_profiles(oauth_home: Path) -> None:
    co.capture_profile("primary", label="A")
    (co.live_auth_path()).write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {"access": "b"}}),
        encoding="utf-8",
    )
    co.capture_profile("fallback", label="B")
    chain = co.oauth_account_chain()
    assert [slot for _, slot in chain] == ["primary", "fallback"]


def test_oauth_chain_dedupes_identical_profiles(oauth_home: Path) -> None:
    co.capture_profile("primary", label="A")
    co.capture_profile("fallback", label="B")
    chain = co.oauth_account_chain()
    assert [slot for _, slot in chain] == ["primary"]


def test_oauth_no_fallback_on_auth_failure(oauth_home: Path) -> None:
    co.capture_profile("primary", label="A")
    (co.live_auth_path()).write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {"access": "b"}}),
        encoding="utf-8",
    )
    co.capture_profile("fallback", label="B")
    calls: list[str | None] = []

    def fn(slot):
        calls.append(slot)
        raise RuntimeError("codex exec failed (exit 1): 401 Unauthorized: token_invalidated")

    with pytest.raises(RuntimeError, match="401"):
        co.call_with_codex_oauth_fallback(fn)
    assert calls == ["primary"]


def test_oauth_no_fallback_on_generic_exec_failure(oauth_home: Path) -> None:
    co.capture_profile("primary", label="A")
    (co.live_auth_path()).write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {"access": "b"}}),
        encoding="utf-8",
    )
    co.capture_profile("fallback", label="B")
    calls: list[str | None] = []

    def fn(slot):
        calls.append(slot)
        if slot == "primary":
            raise RuntimeError("codex exec failed (exit 1): unknown error")
        return "ok"

    with pytest.raises(RuntimeError, match="unknown error"):
        co.call_with_codex_oauth_fallback(fn)
    assert calls == ["primary"]


def test_probe_captured_profiles(oauth_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    co.capture_profile("primary", label="A")
    monkeypatch.setattr(co, "live_login_status", lambda: (True, "logged in"))

    rows = co.probe_captured_profiles()
    assert len(rows) == 1
    assert rows[0]["ok"] is True
    assert rows[0]["label"] == "A"


def test_oauth_fallback_on_usage_limit(oauth_home: Path) -> None:
    co.capture_profile("primary", label="A")
    (co.live_auth_path()).write_text(
        json.dumps({"auth_mode": "chatgpt", "tokens": {"access": "b"}}),
        encoding="utf-8",
    )
    co.capture_profile("fallback", label="B")
    calls: list[str | None] = []

    def fn(slot):
        calls.append(slot)
        if slot == "primary":
            raise RuntimeError("Codex usage limit reached for account")
        return "ok"

    assert co.call_with_codex_oauth_fallback(fn) == "ok"
    assert calls == ["primary", "fallback"]


def _auth_payload(*, account_id: str = "acct-1", last_refresh: str, token: str) -> str:
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {"account_id": account_id, "refresh_token": token},
            "last_refresh": last_refresh,
        }
    )


def test_apply_profile_keeps_fresher_live_same_account(oauth_home: Path) -> None:
    """Rotated/re-logged-in live token must never be stomped by an older snapshot."""
    live = co.live_auth_path()
    live.write_text(_auth_payload(last_refresh="2026-06-19T10:00:00Z", token="old"), encoding="utf-8")
    co.capture_profile("primary", label="A")
    live.write_text(_auth_payload(last_refresh="2026-07-03T09:00:00Z", token="rotated"), encoding="utf-8")

    co.apply_profile("primary")

    assert json.loads(live.read_text(encoding="utf-8"))["tokens"]["refresh_token"] == "rotated"
    snap = json.loads(co.profile_auth_path("primary").read_text(encoding="utf-8"))
    assert snap["tokens"]["refresh_token"] == "rotated"


def test_apply_profile_still_applies_for_different_account(oauth_home: Path) -> None:
    live = co.live_auth_path()
    live.write_text(
        _auth_payload(account_id="acct-A", last_refresh="2026-06-19T10:00:00Z", token="a"),
        encoding="utf-8",
    )
    co.capture_profile("primary", label="A")
    live.write_text(
        _auth_payload(account_id="acct-B", last_refresh="2026-07-03T09:00:00Z", token="b"),
        encoding="utf-8",
    )

    co.apply_profile("primary")

    assert json.loads(live.read_text(encoding="utf-8"))["tokens"]["refresh_token"] == "a"


def test_oauth_fallback_syncs_rotated_token_back_to_snapshot(oauth_home: Path) -> None:
    live = co.live_auth_path()
    live.write_text(_auth_payload(last_refresh="2026-06-19T10:00:00Z", token="old"), encoding="utf-8")
    co.capture_profile("primary", label="A")

    def fn(slot):
        # codex CLI refreshes mid-call: rotates the refresh token in live auth.json
        live.write_text(
            _auth_payload(last_refresh="2026-07-03T09:00:00Z", token="rotated"),
            encoding="utf-8",
        )
        return "ok"

    assert co.call_with_codex_oauth_fallback(fn) == "ok"
    snap = json.loads(co.profile_auth_path("primary").read_text(encoding="utf-8"))
    assert snap["tokens"]["refresh_token"] == "rotated"


def test_revoked_marker_clears_on_newer_last_refresh_despite_old_mtime(oauth_home: Path) -> None:
    """copy2 preserves mtime, so marker auto-clear must also compare token content."""
    import os

    live = co.live_auth_path()
    co.mark_codex_auth_revoked("boom")
    live.write_text(_auth_payload(last_refresh="2100-01-01T00:00:00Z", token="new"), encoding="utf-8")
    old = co.auth_revoked_marker_path().stat().st_mtime + 10
    os.utime(live, (old - 100, old - 100))  # mtime older than marker (copy2 restore)

    assert co.codex_auth_revoked_detail() is None
    assert not co.auth_revoked_marker_path().is_file()


def test_oauth_only_providers_strip_api_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / ".agent-lab"
    cfg.mkdir()
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: cfg)
    save_credentials(
        {
            "cursor": {"primary": "c1", "fallback": ""},
            "claude": {"primary": "bad", "fallback": "also-bad"},
            "codex": {"primary": "", "fallback": "not-a-key"},
        }
    )
    data = load_credentials()
    assert data["claude"]["primary"] == ""
    assert data["codex"]["fallback"] == ""
    assert get_credential_chain("claude") == []
    assert get_credential_chain("codex") == []
    assert get_credential_chain("cursor") == [("메인", "c1")]
