"""G002 — account_chain (auth_kind-branched) + usage_monitor (cooldown, capability-aware)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import agent_lab.app_config as app_config

    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    return tmp_path


# --- usage_monitor.should_preempt: capability-aware, honest local heuristic ---


def test_should_preempt_only_for_usage_exposing() -> None:
    from agent_lab import usage_monitor as um

    # OAuth/CLI providers are reactive-only -> never preempt, regardless of signal.
    assert um.should_preempt("codex", spent_usd=100.0, budget_usd=1.0) is False
    assert um.should_preempt("claude", used_fraction=1.0) is False


def test_should_preempt_budget_cap() -> None:
    from agent_lab import usage_monitor as um

    assert um.should_preempt("kimi", spent_usd=0.95, budget_usd=1.0, threshold=0.9) is True
    assert um.should_preempt("kimi", spent_usd=0.5, budget_usd=1.0, threshold=0.9) is False
    # no signal -> no preempt (honesty)
    assert um.should_preempt("kimi") is False


def test_should_preempt_usage_header_precedence() -> None:
    from agent_lab import usage_monitor as um

    assert um.should_preempt("cursor", used_fraction=0.95, threshold=0.9) is True
    assert um.should_preempt("cursor", used_fraction=0.5, threshold=0.9) is False


def test_provider_spent_usd_reads_ledger() -> None:
    from agent_lab import usage_monitor as um

    run = {"cost_ledger": {"by_agent": {"kimi": {"cost_usd": 1.25}}}}
    assert um.provider_spent_usd(run, "kimi") == 1.25
    assert um.provider_spent_usd(run, "cursor") == 0.0
    assert um.provider_spent_usd(None, "kimi") == 0.0


# --- cooldown: only on credential failure; local exempt ---


def test_mark_exhausted_only_on_credential_failure(cfg: Path) -> None:
    from agent_lab import credential_store as cs
    from agent_lab import usage_monitor as um

    cs.set_provider_accounts("kimi", [{"label": "k1", "secret_or_profile_ref": "sk-1", "priority": 1}])
    # generic error -> no cooldown
    assert um.mark_exhausted("kimi", "k1", error=ValueError("boom"), now=1000.0) is False
    assert um.cooldown_active("kimi", "k1", now=1001.0) is False
    # credential failure -> cooldown applied
    assert um.mark_exhausted("kimi", "k1", error=RuntimeError("401 unauthorized"), now=1000.0) is True
    assert um.cooldown_active("kimi", "k1", now=1001.0) is True


def test_local_fallback_cooldown_exempt(cfg: Path) -> None:
    from agent_lab import usage_monitor as um

    # local is cooldown-exempt -> never cooled, guaranteeing >=1 agent.
    assert um.mark_exhausted("local", "l1", error=RuntimeError("401"), force=True) is False
    assert um.cooldown_active("local", "l1") is False


# --- account_chain: auth_kind branching ---


def test_is_rotating_by_auth_kind() -> None:
    from agent_lab import account_chain as ac

    assert ac.is_rotating("kimi") is True
    assert ac.is_rotating("cursor") is True
    assert ac.is_rotating("local") is True
    assert ac.is_rotating("codex") is False
    assert ac.is_rotating("claude") is False


def test_oauth_usable_chain_single_profile(cfg: Path) -> None:
    from agent_lab import account_chain as ac
    from agent_lab import credential_store as cs

    cs.set_provider_accounts(
        "codex",
        [
            {"label": "p1", "secret_or_profile_ref": "profile-1", "priority": 1},
            {"label": "p2", "secret_or_profile_ref": "profile-2", "priority": 2},
        ],
    )
    chain = ac.usable_chain("codex")
    # oauth -> at most ONE active profile, never a rotation chain
    assert len(chain) == 1
    assert chain[0][0] == "p1"


def test_api_usable_chain_rotates(cfg: Path) -> None:
    from agent_lab import account_chain as ac
    from agent_lab import credential_store as cs

    cs.set_provider_accounts(
        "kimi",
        [
            {"label": "k1", "secret_or_profile_ref": "sk-1", "priority": 1},
            {"label": "k2", "secret_or_profile_ref": "sk-2", "priority": 2},
        ],
    )
    chain = ac.usable_chain("kimi")
    assert [s for _, s in chain] == ["sk-1", "sk-2"]


def test_api_inturn_rotation_on_credential_failure(cfg: Path) -> None:
    from agent_lab import account_chain as ac
    from agent_lab import credential_store as cs

    cs.set_provider_accounts(
        "kimi",
        [
            {"label": "k1", "secret_or_profile_ref": "sk-1", "priority": 1},
            {"label": "k2", "secret_or_profile_ref": "sk-2", "priority": 2},
        ],
    )
    tried: list[str | None] = []

    def fn(secret: str | None) -> str:
        tried.append(secret)
        if secret == "sk-1":
            raise RuntimeError("401 unauthorized")
        return "ok"

    assert ac.call_with_account_chain("kimi", fn, now=1000.0) == "ok"
    assert tried == ["sk-1", "sk-2"]  # rotated in-turn


def test_oauth_no_inturn_rotation(cfg: Path) -> None:
    from agent_lab import account_chain as ac
    from agent_lab import credential_store as cs

    cs.set_provider_accounts(
        "codex",
        [
            {"label": "p1", "secret_or_profile_ref": "profile-1", "priority": 1},
            {"label": "p2", "secret_or_profile_ref": "profile-2", "priority": 2},
        ],
    )
    tried: list[str | None] = []

    def fn(ref: str | None) -> str:
        tried.append(ref)
        raise RuntimeError("401 unauthorized")

    with pytest.raises(RuntimeError):
        ac.call_with_account_chain("codex", fn, now=1000.0)
    # exactly one attempt — no in-turn key rotation for oauth
    assert len(tried) == 1
