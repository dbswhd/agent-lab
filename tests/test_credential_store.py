from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_lab import credential_store as cs


@pytest.fixture
def creds_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / ".agent-lab"
    cfg.mkdir()
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: cfg)
    monkeypatch.setenv("HOME", str(tmp_path))
    return cfg


def test_save_load_roundtrip(creds_home: Path) -> None:
    data = cs._empty_store()
    data["cursor"]["primary"] = "cursor-main-key"
    data["cursor"]["fallback"] = "cursor-sub-key"
    data["cursor"]["primary_label"] = "Work"
    data["cursor"]["fallback_label"] = "Personal"
    path = cs.save_credentials(data)
    assert path.is_file()
    loaded = cs.load_credentials()
    assert loaded["cursor"]["primary"] == "cursor-main-key"
    assert loaded["cursor"]["fallback"] == "cursor-sub-key"
    assert loaded["cursor"]["primary_label"] == "Work"


def test_credential_chain_dedupes(creds_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cs.save_credentials(
        {
            "cursor": {"primary": "same-key", "fallback": ""},
            "claude": cs._empty_store()["claude"],
            "codex": cs._empty_store()["codex"],
        }
    )
    monkeypatch.setenv("CURSOR_API_KEY", "same-key")
    chain = cs.get_credential_chain("cursor")
    assert len(chain) == 1
    assert chain[0][1] == "same-key"


def test_call_with_fallback_on_auth_error(creds_home: Path) -> None:
    cs.save_credentials(
        {
            "cursor": {"primary": "bad-key", "fallback": "good-key"},
            "claude": cs._empty_store()["claude"],
            "codex": cs._empty_store()["codex"],
        }
    )
    calls: list[str | None] = []

    def fn(key: str | None) -> str:
        calls.append(key)
        if key == "bad-key":
            raise RuntimeError("401 unauthorized invalid api key")
        return f"ok:{key}"

    assert cs.call_with_credential_fallback("cursor", fn) == "ok:good-key"
    assert calls == ["bad-key", "good-key"]


def test_is_credential_failure() -> None:
    assert cs.is_credential_failure(RuntimeError("401 unauthorized"))
    assert cs.is_credential_failure("session limit reached")
    assert not cs.is_credential_failure(RuntimeError("connection reset"))


def test_mask_secret() -> None:
    assert cs.mask_secret("") is None
    assert cs.mask_secret("short") == "••••"
    masked = cs.mask_secret("sk-ant-api03-abcdefghij")
    assert masked is not None
    assert masked.endswith("ghij")


def test_apply_credentials_to_env(creds_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    cs.save_credentials(
        {
            "cursor": {"primary": "env-sync-key", "fallback": ""},
            "claude": cs._empty_store()["claude"],
            "codex": cs._empty_store()["codex"],
        }
    )
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    cs.apply_credentials_to_env()
    assert os.getenv("CURSOR_API_KEY") == "env-sync-key"


def test_public_payload_masks_secrets(creds_home: Path) -> None:
    cs.save_credentials(
        {
            "cursor": {"primary": "abcdefghijklmnop", "fallback": ""},
            "claude": cs._empty_store()["claude"],
            "codex": cs._empty_store()["codex"],
        }
    )
    payload = cs.public_credentials_payload()
    cursor = next(a for a in payload["agents"] if a["id"] == "cursor")
    assert cursor["has_primary"] is True
    assert cursor["primary_masked"] is not None
    assert "abcdef" not in (cursor["primary_masked"] or "")


def test_credentials_api(creds_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.server.main import app

    # legacy Settings credential write path = OFF-parity (dynamic room moves it to slash)
    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "0")
    client = TestClient(app)
    get_res = client.get("/api/settings/credentials")
    assert get_res.status_code == 200
    body = get_res.json()
    assert body["ok"] is True
    assert len(body["agents"]) == 3

    put_res = client.put(
        "/api/settings/credentials",
        json={
            "cursor": {
                "primary": "api-test-key",
                "primary_label": "Test",
            }
        },
    )
    assert put_res.status_code == 200
    put_body = put_res.json()
    assert put_body.get("saved") is True
    cursor = next(a for a in put_body["agents"] if a["id"] == "cursor")
    assert cursor["has_primary"] is True
    assert cursor["primary_label"] == "Test"
