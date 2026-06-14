from __future__ import annotations

from dataclasses import replace

from agent_lab.model_policy import (
    agent_model_profiles,
    loop_blockers,
    loop_ready,
    team_ready,
)


def test_default_agent_model_profiles_are_team_ready() -> None:
    profiles = agent_model_profiles()
    assert set(profiles) == {"cursor", "codex", "claude"}
    assert all(team_ready(profile) for profile in profiles.values())


def test_default_agent_profiles_are_loop_ready() -> None:
    # cursor/codex/claude all support tools + inbox MCP + JSON envelope at runtime,
    # so the default team can enter Loop without readiness gating.
    profiles = agent_model_profiles()
    assert all(loop_ready(profile) for profile in profiles.values())


def test_loop_ready_requires_tools_inbox_and_envelope() -> None:
    base = agent_model_profiles()["cursor"]
    assert loop_ready(base) is True

    assert loop_blockers(replace(base, supports_tools=False)) == ("supports_tools",)
    assert loop_blockers(replace(base, supports_inbox_mcp=False)) == ("supports_inbox_mcp",)
    assert loop_blockers(replace(base, supports_json_envelope=False)) == (
        "supports_json_envelope",
    )
    assert loop_ready(replace(base, supports_tools=False)) is False

