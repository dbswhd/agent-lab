"""Follow-up — Kimi Work peer provider (P0 mock) + substitution priority."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_room_model_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import agent_lab.app_config as app_config

    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    monkeypatch.delenv("AGENT_LAB_ROOM_MODELS", raising=False)
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    monkeypatch.setenv("KIMI_SHARE_DIR", str(tmp_path / "isolated-daimon-share"))


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import agent_lab.app_config as app_config

    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    return tmp_path


def test_extract_conversation_key_live_shape() -> None:
    from agent_lab.kimi_work_session import extract_conversation_key

    created = {
        "activeConversationKey": "main:conversation:abc-123",
        "conversation": {"conversationKey": "main:conversation:abc-123"},
    }
    assert extract_conversation_key(created) == "main:conversation:abc-123"


def test_build_agent_preflight_includes_kimi_work_when_dynamic(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.agent_preflight import build_agent_preflight

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "1")
    rows = build_agent_preflight(probe_bridge=False)
    ids = [r["id"] for r in rows]
    assert "kimi_work" in ids
    kw = next(r for r in rows if r["id"] == "kimi_work")
    assert kw["ready"] is True


def test_kimi_work_mock_reply_streams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab import kimi_work_provider as kwp

    chunks: list[str] = []

    def on_bridge(event: str, payload: dict) -> None:
        if event == "text":
            chunks.append(str(payload.get("text") or ""))

    text = kwp.respond("sys", "hello", session_folder=tmp_path, on_bridge_event=on_bridge)
    assert text.startswith("[mock:Kimi Work]")
    assert chunks
    assert chunks[-1] == text
    assert (tmp_path / "kimi_work.json").is_file()


def test_kimi_work_tunable_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import kimi_work_provider as kwp

    monkeypatch.delenv("AGENT_LAB_KIMI_WORK_MODEL", raising=False)
    assert kwp.kimi_work_model() == "k2p6"
    monkeypatch.setenv("AGENT_LAB_KIMI_WORK_MODEL", "kimi-coding/k2p6")
    assert kwp.model_label() == "kimi-work:kimi-coding/k2p6"


def test_kimi_work_availability_mock_vs_live(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import kimi_work_provider as kwp

    assert kwp.is_configured() is False
    assert kwp.is_available() is False

    share = cfg / "daimon-share-mock"
    monkeypatch.setenv("KIMI_SHARE_DIR", str(share))
    (share / "daimon").mkdir(parents=True)
    (share / "daimon" / "config.json").write_text("{}", encoding="utf-8")
    assert kwp.is_configured() is True
    assert kwp.is_available() is True


def test_registry_kimi_work_invokable_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.agents import registry

    assert "[mock:Kimi Work]" in registry.call_agent_reply("kimi_work", "sys", "ping").text
    assert registry.label("kimi_work") == "Kimi Work"


def test_agent_ids_off_parity() -> None:
    from agent_lab.agents import registry

    assert registry.AGENT_IDS == ("cursor", "codex", "claude")


def test_agent_health_kimi_work_ready_when_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.agent_health import agent_health_row

    row = agent_health_row("kimi_work", probe_bridge=True)
    assert row["configured"] is True
    assert row["bridge"] == "ok"
    assert row["ready"] is True


def test_dynamic_available_includes_kimi_work_when_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab import agent_roster as ar

    ids = ar.dynamic_available_ids(lambda: ["claude"])
    assert "kimi_work" in ids and "local" in ids


def test_resolve_substitutes_kimi_work_before_kimi(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab import agent_roster as ar
    from agent_lab import credential_store as cs

    cs.set_provider_accounts("kimi", [{"label": "k1", "secret_or_profile_ref": "sk-1", "priority": 1}])
    roster = ar.resolve_active_agents(None, lambda: ["claude"], enabled=True)
    assert roster[0] == "claude"
    assert roster[1] == "kimi_work"
    assert "kimi" not in roster[:2]


def test_provider_registry_kimi_work_peer() -> None:
    from agent_lab import provider_registry as pr

    assert "kimi_work" in pr.provider_ids()
    assert pr.auth_kind("kimi_work") == "peer"
    assert pr.is_usage_exposing("kimi_work") is True
    assert pr.supports_inturn_key_rotation("kimi_work") is False
    assert pr.DEFAULT_SUBSTITUTION_PRIORITY == ("kimi_work", "kimi", "local")
