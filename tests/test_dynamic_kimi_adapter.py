"""Follow-up — KIMI live adapter + live substitution (KIMI->local) priority."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_room_model_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import agent_lab.app_config as app_config

    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    monkeypatch.delenv("AGENT_LAB_ROOM_MODELS", raising=False)


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import agent_lab.app_config as app_config

    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    return tmp_path


def test_kimi_mock_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab import kimi_provider as kp

    assert kp.is_available() is True
    assert kp.respond("sys", "hello").startswith("[mock:KIMI]")


def test_kimi_tunable_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import kimi_provider as kp

    monkeypatch.delenv("AGENT_LAB_KIMI_MODEL", raising=False)
    assert kp.kimi_model() == "kimi-k2"
    monkeypatch.setenv("AGENT_LAB_KIMI_MODEL", "kimi-k2.7-code")
    assert kp.model_label() == "kimi:kimi-k2.7-code"


def test_kimi_availability_requires_chain_when_live(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    from agent_lab import credential_store as cs
    from agent_lab import kimi_provider as kp

    assert kp.is_available() is False  # no accounts yet
    cs.set_provider_accounts("kimi", [{"label": "k1", "secret_or_profile_ref": "sk-1", "priority": 1}])
    assert kp.is_available() is True


def test_registry_kimi_invokable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.agents import registry

    assert "[mock:KIMI]" in registry.call_agent_reply("kimi", "sys", "ping").text
    assert registry.label("kimi") == "KIMI"


def test_dynamic_available_includes_kimi_when_keyed(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    from agent_lab import agent_roster as ar
    from agent_lab import credential_store as cs

    # no kimi accounts -> not in dynamic availability
    assert "kimi" not in ar.dynamic_available_ids(lambda: ["claude"])
    cs.set_provider_accounts("kimi", [{"label": "k1", "secret_or_profile_ref": "sk-1", "priority": 1}])
    ids = ar.dynamic_available_ids(lambda: ["claude"])
    assert "kimi" in ids and "local" in ids


def test_resolve_substitutes_kimi_before_local(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    from agent_lab import agent_roster as ar
    from agent_lab import credential_store as cs

    cs.set_provider_accounts("kimi", [{"label": "k1", "secret_or_profile_ref": "sk-1", "priority": 1}])
    # 2 of 3 cloud exhausted (only claude) + kimi keyed -> kimi fills before local
    roster = ar.resolve_active_agents(None, lambda: ["claude"], enabled=True)
    assert roster[:2] == ["claude", "kimi"]
    assert "kimi" in roster


def test_resolve_falls_to_local_without_kimi_chain(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    from agent_lab import agent_roster as ar

    # kimi has no chain -> excluded; local floor still fills
    roster = ar.resolve_active_agents(None, lambda: ["claude"], enabled=True)
    assert "kimi" not in roster and "local" in roster


def test_kimi_first_class_streams_and_emits_activity(cfg: Path) -> None:
    """Phase 2: KIMI is a first-class room substitute (activity + streaming)."""
    import os

    os.environ["AGENT_LAB_MOCK_AGENTS"] = "1"
    try:
        from agent_lab import kimi_provider as kp

        acts: list[str] = []
        chunks: list[tuple[str, str]] = []
        text = kp.respond(
            "sys",
            "stream this please across multiple chunks now",
            on_activity=acts.append,
            on_bridge_event=lambda ev, d: chunks.append((ev, d.get("text", ""))),
            session_folder=None,
            request_structured_envelope=True,
        )
        assert acts and "kimi:" in acts[0]
        assert chunks and all(ev == "text" for ev, _ in chunks)
        assert "".join(t for _, t in chunks) == text
    finally:
        os.environ.pop("AGENT_LAB_MOCK_AGENTS", None)
