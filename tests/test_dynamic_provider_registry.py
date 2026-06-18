"""G001 — provider_registry catalog + additive multi-account chain (get_account_chain)."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_registry_catalog() -> None:
    from agent_lab import provider_registry as pr

    ids = set(pr.provider_ids())
    assert {"cursor", "claude", "codex", "kimi", "local"} <= ids
    # auth_kind seam
    assert pr.auth_kind("kimi") == "api"
    assert pr.auth_kind("cursor") == "api"
    assert pr.auth_kind("claude") == "oauth"
    assert pr.auth_kind("codex") == "oauth"
    assert pr.auth_kind("local") == "local"
    # usage exposing
    assert pr.is_usage_exposing("kimi") is True
    assert pr.is_usage_exposing("cursor") is True
    assert pr.is_usage_exposing("claude") is False
    assert pr.is_usage_exposing("codex") is False
    # in-turn rotation seam: api/local rotate, oauth/cli do not
    assert pr.supports_inturn_key_rotation("kimi") is True
    assert pr.supports_inturn_key_rotation("local") is True
    assert pr.supports_inturn_key_rotation("claude") is False
    assert pr.supports_inturn_key_rotation("codex") is False
    # floor provider
    assert pr.is_always_available("local") is True
    assert pr.is_cooldown_exempt("local") is True
    assert pr.is_always_available("kimi") is False


def test_default_roster_byte_stable() -> None:
    from agent_lab import provider_registry as pr

    assert pr.DEFAULT_ROSTER == ("cursor", "codex", "claude")
    assert pr.DEFAULT_SUBSTITUTION_PRIORITY == ("kimi", "local")


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import agent_lab.app_config as app_config

    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    return tmp_path


def test_set_get_provider_accounts_roundtrip(cfg: Path) -> None:
    from agent_lab import credential_store as cs

    cs.set_provider_accounts(
        "kimi",
        [
            {"label": "k2", "secret_or_profile_ref": "sk-2", "priority": 2},
            {"label": "k1", "secret_or_profile_ref": "sk-1", "priority": 1},
        ],
    )
    got = cs.get_provider_accounts("kimi")
    assert {a["label"] for a in got} == {"k1", "k2"}


def test_get_account_chain_priority_order_api(cfg: Path) -> None:
    from agent_lab import credential_store as cs

    cs.set_provider_accounts(
        "kimi",
        [
            {"label": "second", "secret_or_profile_ref": "sk-2", "priority": 2},
            {"label": "first", "secret_or_profile_ref": "sk-1", "priority": 1},
        ],
    )
    chain = cs.get_account_chain("kimi")
    assert [label for label, _ in chain] == ["first", "second"]
    assert [secret for _, secret in chain] == ["sk-1", "sk-2"]


def test_get_account_chain_cooldown_filter(cfg: Path) -> None:
    from agent_lab import credential_store as cs

    cs.set_provider_accounts(
        "kimi",
        [
            {"label": "cool", "secret_or_profile_ref": "sk-cool", "priority": 1, "cooldown_until": 9_999_999_999.0},
            {"label": "ready", "secret_or_profile_ref": "sk-ready", "priority": 2, "cooldown_until": 0.0},
        ],
    )
    chain = cs.get_account_chain("kimi", now=1_000.0)
    assert [label for label, _ in chain] == ["ready"]


def test_get_account_chain_oauth_excludes_secrets(cfg: Path) -> None:
    from agent_lab import credential_store as cs

    # OAuth providers: accounts[] hold profile refs, not in-turn secrets -> empty secret chain.
    cs.set_provider_accounts(
        "codex",
        [{"label": "profile-a", "secret_or_profile_ref": "profile-a", "priority": 1}],
    )
    assert cs.get_account_chain("codex") == []


def test_get_account_chain_appends_legacy_for_typed(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import credential_store as cs

    # cursor is api/typed: accounts[] first, then legacy credentials.toml chain.
    monkeypatch.setenv("CURSOR_API_KEY", "legacy-cursor")
    cs.set_provider_accounts("cursor", [{"label": "acct1", "secret_or_profile_ref": "sk-acct1", "priority": 1}])
    chain = cs.get_account_chain("cursor")
    secrets = [s for _, s in chain]
    assert secrets[0] == "sk-acct1"
    assert "legacy-cursor" in secrets
