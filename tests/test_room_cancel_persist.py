"""Cancelled room turns persist partial chat to disk."""

from __future__ import annotations

import json
from pathlib import Path

from agent_mocks import patch_call_agent_reply


def test_cancelled_turn_persists_user_and_partial_agents(monkeypatch, tmp_path):
    from agent_lab import room
    from agent_lab.room import parallel_rounds
    from agent_lab.run.control import RoomRunCancelled, clear_cancel, request_cancel
    from agent_lab.room.session_persist import load_session_messages

    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    call_count = {"codex": 0}

    def fake_call_agent(agent, _system, user, **kwargs):
        if agent == "cursor":
            return '```agent-envelope\n{"act":"PROPOSE","refs":[],"confidence":0.8}\n```\ncursor ok'
        if agent == "codex":
            call_count["codex"] += 1
            request_cancel()
            raise RoomRunCancelled("run cancelled by user")
        raise AssertionError(f"unexpected agent: {agent}")

    patch_call_agent_reply(monkeypatch, fake_call_agent)

    real_parallel = parallel_rounds.run_parallel_round

    def sequential_parallel_round(*args, **kwargs):
        agents = kwargs.get("agents")
        if agents is None and len(args) > 2:
            agents = args[2]
        replies = []
        for aid in agents or []:
            replies.extend(real_parallel(*args, **{**kwargs, "agents": [aid]}))
        return replies

    monkeypatch.setattr(parallel_rounds, "run_parallel_round", sequential_parallel_round)
    clear_cancel()

    folder, messages, _plan_md = room.run_room(
        "Internal structure review",
        agents=["cursor", "codex"],
        synthesize=False,
        parallel_rounds=1,
        sessions_base=tmp_path,
        turn_profile="analyze",
    )

    clear_cancel()
    assert call_count["codex"] == 1
    assert any(m.role == "user" for m in messages)
    assert any(m.role == "agent" and m.agent == "cursor" for m in messages)

    reloaded = load_session_messages(folder)
    assert any(m.role == "user" for m in reloaded)
    assert any(m.role == "agent" and m.agent == "cursor" for m in reloaded)

    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["message_count"] >= 2


def test_persist_chat_checkpoint_writes_without_full_turn(monkeypatch, tmp_path):
    from agent_lab.room.messages import ChatMessage
    from agent_lab.room.session_persist import load_session_messages, persist_chat_checkpoint

    folder = tmp_path / "sess-checkpoint"
    folder.mkdir()
    (folder / "run.json").write_text('{"topic":"t","turns":[]}\n', encoding="utf-8")
    msgs = [
        ChatMessage(role="user", agent=None, content="hello"),
        ChatMessage(role="agent", agent="cursor", content="partial", parallel_round=1),
    ]
    persist_chat_checkpoint(folder, msgs, topic="hello")
    loaded = load_session_messages(folder)
    assert len(loaded) == 2
    assert loaded[1].agent == "cursor"
