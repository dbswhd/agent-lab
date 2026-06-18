"""G003 — dynamic agent roster (flag-gated) + OFF-parity named test."""
from __future__ import annotations

import pytest


def test_dynamic_room_flag_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import agent_roster as ar

    monkeypatch.delenv("AGENT_LAB_DYNAMIC_ROOM", raising=False)
    assert ar.dynamic_room_enabled() is False
    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "1")
    assert ar.dynamic_room_enabled() is True
    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "off")
    assert ar.dynamic_room_enabled() is False


def test_select_roster_default_composition() -> None:
    from agent_lab import agent_roster as ar

    roster = ar.select_roster(available_ids=["cursor", "codex", "claude", "kimi", "local"])
    assert roster == ["cursor", "codex", "claude"]


def test_select_roster_substitution_priority() -> None:
    from agent_lab import agent_roster as ar

    # cursor seat unavailable -> fill from substitution priority (kimi before local)
    roster = ar.select_roster(available_ids=["codex", "claude", "kimi", "local"])
    assert roster == ["codex", "claude", "kimi"]


def test_select_roster_falls_through_to_local() -> None:
    from agent_lab import agent_roster as ar

    # only one default available + local floor -> substitution adds local last
    roster = ar.select_roster(available_ids=["claude", "local"])
    assert roster == ["claude", "local"]


def test_select_roster_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import agent_roster as ar

    monkeypatch.setenv("AGENT_LAB_ROOM_MODELS", "cursor,kimi,claude")
    roster = ar.select_roster(available_ids=["cursor", "kimi", "claude", "codex"])
    assert roster == ["cursor", "kimi", "claude"]


def test_select_roster_substitution_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import agent_roster as ar

    monkeypatch.setenv("AGENT_LAB_ROOM_SUBSTITUTION", "local,kimi")
    roster = ar.select_roster(available_ids=["codex", "claude", "kimi", "local"])
    # cursor seat empty -> substitution override puts local before kimi
    assert roster == ["codex", "claude", "local"]


def test_off_parity_default_roster(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flag unset == current ["cursor","codex","claude"] behavior, byte-stable."""
    monkeypatch.delenv("AGENT_LAB_DYNAMIC_ROOM", raising=False)
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab import agent_roster as ar
    from agent_lab.agents.registry import available_agents

    resolved = ar.resolve_active_agents(None, available_agents)
    assert resolved == ["cursor", "codex", "claude"]
    # explicit agents passthrough unchanged when OFF
    assert ar.resolve_active_agents(["codex"], available_agents) == ["codex"]


def test_off_parity_passthrough_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_DYNAMIC_ROOM", raising=False)
    from agent_lab import agent_roster as ar

    fake_available = lambda: ["cursor", "codex", "claude"]  # noqa: E731
    assert ar.resolve_active_agents(["claude", "cursor"], fake_available) == ["claude", "cursor"]


def test_resolve_on_restricts_to_invokable_agentids() -> None:
    from agent_lab import agent_roster as ar

    # ON, but available_fn only yields invokable AgentIds -> kimi/local never leak live.
    fake_available = lambda: ["codex", "claude"]  # noqa: E731
    resolved = ar.resolve_active_agents(None, fake_available, enabled=True)
    assert resolved == ["codex", "claude"]
    assert "kimi" not in resolved and "local" not in resolved
