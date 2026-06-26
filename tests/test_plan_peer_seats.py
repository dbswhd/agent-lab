"""Plan peer-review seat mapping (P1-a)."""

from __future__ import annotations

from typing import Any

import pytest

from agent_lab.plan_peer_seats import (
    plan_cold_critic_enabled,
    plan_peer_review_seats,
    plan_peer_review_uses_role_lanes,
    plan_scribe_agent,
)


def test_plan_scribe_agent_defaults_to_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROOM_SCRIBE_AGENT", raising=False)
    assert plan_scribe_agent() == "claude"
    monkeypatch.setenv("ROOM_SCRIBE_AGENT", "codex")
    assert plan_scribe_agent() == "codex"


def test_supervisor_peer_seats_codex_claude_exclude_scribe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOM_SCRIBE_AGENT", "cursor")
    run_meta = {"room_preset": "supervisor"}
    seats = plan_peer_review_seats(
        ["cursor", "codex", "claude"],
        run_meta=run_meta,
    )
    assert seats == ["codex", "claude"]


def test_supervisor_peer_seats_when_scribe_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOM_SCRIBE_AGENT", "codex")
    run_meta = {"room_preset": "supervisor"}
    seats = plan_peer_review_seats(["codex", "claude", "cursor"], run_meta=run_meta)
    assert seats == ["claude"]


def test_non_supervisor_excludes_scribe_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOM_SCRIBE_AGENT", "claude")
    seats = plan_peer_review_seats(["codex", "claude", "cursor"], run_meta={})
    assert seats == ["codex", "cursor"]


def test_cold_critic_on_for_supervisor_without_antidrift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ANTIDRIFT", raising=False)
    monkeypatch.delenv("AGENT_LAB_PLAN_COLD_CRITIC", raising=False)
    assert plan_cold_critic_enabled(run_meta={"room_preset": "supervisor"}) is True
    assert plan_cold_critic_enabled(run_meta={}) is False


def test_cold_critic_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ANTIDRIFT", raising=False)
    monkeypatch.setenv("AGENT_LAB_PLAN_COLD_CRITIC", "1")
    assert plan_cold_critic_enabled(run_meta={}) is True


def test_supervisor_uses_role_lanes() -> None:
    assert plan_peer_review_uses_role_lanes(run_meta={"room_preset": "supervisor"}) is True
    assert plan_peer_review_uses_role_lanes(run_meta={}) is False


def test_supervisor_peer_review_rounds_include_cold_critic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    import agent_lab.plan_workflow as pw

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("ROOM_SCRIBE_AGENT", "cursor")
    monkeypatch.delenv("AGENT_LAB_ANTIDRIFT", raising=False)
    rounds: list[tuple[list[str], list[Any], str]] = []

    def _fake_round(topic: str, messages: Any, agents: Any = None, **kwargs: Any) -> list[Any]:
        rounds.append(
            (
                [str(a) for a in (agents or [])],
                list(messages or []),
                str(kwargs.get("extra_follow_up") or ""),
            )
        )
        return []

    monkeypatch.setattr("agent_lab.room.run_parallel_round", _fake_round)
    folder = tmp_path / "sess"
    folder.mkdir()
    pw.run_plan_peer_review_round(
        folder,
        topic="t",
        messages=["prior"],
        agents=["codex", "claude", "cursor"],
        permissions=None,
        run_meta={"room_preset": "supervisor"},
        plan_md="# plan",
    )
    assert len(rounds) == 3
    assert rounds[0][0] == ["codex"]
    assert "architect" in rounds[0][2]
    assert rounds[1][0] == ["claude"]
    assert "critic" in rounds[1][2]
    assert rounds[2][1] == []
    assert "fresh-eyes" in rounds[2][2]
