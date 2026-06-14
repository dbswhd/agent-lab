"""Sync pause (M4) — pending question halts further auto discuss rounds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from agent_lab.inbox_harvest import (
    harvest_and_check_pause,
    inbox_mode,
    should_pause_discuss,
)


@dataclass
class _Msg:
    role: str
    agent: str | None = None
    content: str = ""
    envelope: dict[str, Any] | None = None


def _fork_msg(agent: str) -> _Msg:
    block = (
        "```decision-fork\n"
        + json.dumps(
            {"topic": "스윕 범위", "options": [
                {"label": "VU만", "refs": ["L42"]},
                {"label": "VU+Theme", "refs": ["L51"]},
            ]},
            ensure_ascii=False,
        )
        + "\n```"
    )
    return _Msg(role="agent", agent=agent, content=block)


def test_inbox_mode_default_sync(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGENT_LAB_INBOX_MODE", raising=False)
    assert inbox_mode() == "sync"


def test_inbox_mode_soft(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_INBOX_MODE", "soft")
    assert inbox_mode() == "soft"


def test_inbox_mode_unknown_falls_back_to_sync(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_INBOX_MODE", "weird")
    assert inbox_mode() == "sync"


def test_should_pause_sync_with_pending(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGENT_LAB_INBOX_MODE", raising=False)
    run_meta = {
        "human_inbox": [{"id": "q1", "kind": "question", "status": "pending"}],
    }
    assert should_pause_discuss(run_meta) is True


def test_should_not_pause_without_pending(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGENT_LAB_INBOX_MODE", raising=False)
    run_meta = {
        "human_inbox": [{"id": "q1", "kind": "question", "status": "resolved"}],
    }
    assert should_pause_discuss(run_meta) is False


def test_soft_mode_never_pauses(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_INBOX_MODE", "soft")
    run_meta = {
        "human_inbox": [{"id": "q1", "kind": "question", "status": "pending"}],
    }
    assert should_pause_discuss(run_meta) is False


def test_harvest_and_check_pause_sync(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGENT_LAB_INBOX_MODE", raising=False)
    run_meta: dict[str, Any] = {}
    messages = [_Msg(role="user", content="topic"), _fork_msg("codex")]
    paused = harvest_and_check_pause(run_meta, messages, human_turn=1)
    assert paused is True
    assert run_meta["human_inbox"][0]["kind"] == "question"
    assert run_meta.get("inbox_pending") is True


def test_harvest_and_check_pause_soft_surfaces_without_pausing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("AGENT_LAB_INBOX_MODE", "soft")
    run_meta: dict[str, Any] = {}
    messages = [_Msg(role="user", content="topic"), _fork_msg("codex")]
    paused = harvest_and_check_pause(run_meta, messages, human_turn=1)
    assert paused is False  # soft: surfaced but no pause
    assert run_meta["human_inbox"][0]["kind"] == "question"  # still harvested


def test_harvest_and_check_pause_plan_mode_noop(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AGENT_LAB_INBOX_MODE", raising=False)
    run_meta: dict[str, Any] = {}
    messages = [_Msg(role="user", content="topic"), _fork_msg("codex")]
    paused = harvest_and_check_pause(run_meta, messages, mode="plan")
    assert paused is False
    assert "human_inbox" not in run_meta


def test_session_inbox_mode_overrides_env_sync(monkeypatch: pytest.MonkeyPatch):
    from agent_lab.inbox_harvest import inbox_mode_for_run, should_pause_discuss

    monkeypatch.delenv("AGENT_LAB_INBOX_MODE", raising=False)
    run_meta = {
        "inbox_mode": "soft",
        "human_inbox": [{"id": "q1", "kind": "question", "status": "pending"}],
    }
    assert inbox_mode_for_run(run_meta) == "soft"
    assert should_pause_discuss(run_meta) is False


def test_session_inbox_mode_overrides_env_soft(monkeypatch: pytest.MonkeyPatch):
    from agent_lab.inbox_harvest import inbox_mode_for_run, should_pause_discuss

    monkeypatch.setenv("AGENT_LAB_INBOX_MODE", "soft")
    run_meta = {
        "inbox_mode": "sync",
        "human_inbox": [{"id": "q1", "kind": "question", "status": "pending"}],
    }
    assert inbox_mode_for_run(run_meta) == "sync"
    assert should_pause_discuss(run_meta) is True
