"""G006 — local fallback provider + e2e resilience (cloud exhaustion -> >=1 agent)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_room_model_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import agent_lab.app_config as app_config
    from agent_lab import credential_store as cs

    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    monkeypatch.delenv("AGENT_LAB_ROOM_MODELS", raising=False)
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    monkeypatch.setenv("KIMI_SHARE_DIR", str(tmp_path / "isolated-daimon-share"))
    cs.set_provider_accounts("kimi", [])


def test_local_provider_always_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import local_provider as lp

    assert lp.is_available() is True
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    reply = lp.respond("sys", "hello world")
    assert reply.startswith("[mock:Local]") and "hello world" in reply


def test_local_provider_tunable_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import local_provider as lp

    monkeypatch.delenv("AGENT_LAB_LOCAL_MODEL", raising=False)
    assert lp.local_model() == "llama3.2"
    monkeypatch.setenv("AGENT_LAB_LOCAL_MODEL", "qwen2.5")
    assert lp.local_model() == "qwen2.5"
    assert lp.model_label() == "local:qwen2.5"


def test_registry_local_ready_and_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.agents import registry

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    # local is invokable through the registry mock path without KeyError.
    reply = registry.call_agent_reply("local", "sys", "ping")
    assert "[mock:Local]" in reply.text


def test_dynamic_available_ids_includes_local_floor() -> None:
    from agent_lab.agent import roster as ar

    ids = ar.dynamic_available_ids(lambda: ["cursor", "codex", "claude"])
    assert "local" in ids
    # full cloud exhaustion still yields the local floor
    assert ar.dynamic_available_ids(lambda: []) == ["local"]


def test_resolve_full_cloud_exhaustion_keeps_one(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.agent import roster as ar

    roster = ar.resolve_active_agents(None, lambda: [], enabled=True)
    assert roster == ["local"]  # >=1 agent guaranteed by the local floor


def test_resolve_two_cloud_exhausted_substitutes_local(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.agent import roster as ar

    # only claude survives -> seat filled by local substitution
    roster = ar.resolve_active_agents(None, lambda: ["claude"], enabled=True)
    assert "claude" in roster and "local" in roster
    assert len(roster) >= 2


def test_consensus_modes_for_degraded_rosters() -> None:
    from agent_lab.consensus_gate import effective_consensus

    assert effective_consensus(["local"])["mode"] == "solo"
    assert effective_consensus(["claude", "local"])["mode"] == "consensus"


def test_e2e_room_completes_with_local_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Full cloud exhaustion: room completes a turn with the local fallback (solo)."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.room import run_room

    folder = tmp_path / "sess-local"
    folder.mkdir()
    out_folder, messages, _plan = run_room(
        "Resilience check: respond briefly.",
        agents=["local"],
        synthesize=False,
        sessions_base=tmp_path,
        session_folder=folder,
        consensus_mode=False,
    )
    # >=1 agent produced a turn without raising
    assert (
        any(
            "Local" in (getattr(m, "agent", "") or getattr(m, "author", "") or "")
            or "[mock:Local]" in (getattr(m, "content", "") or "")
            for m in messages
        )
        or messages
    )


def test_e2e_room_completes_with_degraded_roster(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """2 of 3 cloud exhausted: room completes with surviving cloud + local."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.room import run_room

    folder = tmp_path / "sess-degraded"
    folder.mkdir()
    out_folder, messages, _plan = run_room(
        "Resilience check: respond briefly.",
        agents=["claude", "local"],
        synthesize=False,
        sessions_base=tmp_path,
        session_folder=folder,
        consensus_mode=True,
    )
    assert messages  # turn completed with >=1 agent


def test_local_first_class_streams_and_emits_activity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 2: local is a first-class room substitute (activity + streaming)."""
    from agent_lab import local_provider as lp

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    acts: list[str] = []
    chunks: list[tuple[str, str]] = []
    text = lp.respond(
        "sys",
        "stream this please across multiple chunks now",
        on_activity=acts.append,
        on_bridge_event=lambda ev, d: chunks.append((ev, d.get("text", ""))),
        session_folder=None,  # absorbed
        request_structured_envelope=True,  # absorbed (prompt-carried)
    )
    assert acts and "local:" in acts[0]
    assert chunks and all(ev == "text" for ev, _ in chunks)
    assert "".join(t for _, t in chunks) == text
