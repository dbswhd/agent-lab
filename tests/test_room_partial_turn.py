from __future__ import annotations

import json

from agent_mocks import patch_call_agent_reply


def test_room_turn_partial_preserves_success_and_runs_scribe(monkeypatch, tmp_path):
    from agent_lab import room

    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    scribe_calls: list[str] = []
    events: list[tuple[str, dict]] = []

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            scribe_calls.append(agent)
            assert "Cursor" in user or "cursor ok" in user
            return "## Plan\n\n- keep successful agent response\n"
        if agent == "cursor":
            return '```agent-envelope\n{"act":"PROPOSE","refs":[],"confidence":0.8}\n```\ncursor ok'
        if agent == "claude":
            raise RuntimeError("429 rate limit")
        raise AssertionError(f"unexpected agent: {agent}")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    folder, messages, plan_md = room.run_room(
        "Please discuss a concrete retry implementation plan for this repository.",
        agents=["cursor", "claude"],
        synthesize=True,
        parallel_rounds=1,
        sessions_base=tmp_path,
        on_event=lambda typ, payload: events.append((typ, payload)),
        turn_profile="analyze",
    )

    assert "keep successful agent response" in plan_md
    assert scribe_calls
    assert any(m.role == "agent" and m.agent == "cursor" and "cursor ok" in m.content for m in messages)
    assert any(m.role == "system" and m.agent == "claude" for m in messages)

    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["status"] == "partial"
    assert run["last_turn"]["status"] == "partial"
    assert run["last_turn"]["failed_agents"] == ["claude"]
    assert run["last_turn"]["succeeded_agents"] == ["cursor"]

    event_types = [typ for typ, _payload in events]
    assert "agent_error" in event_types
    assert "turn_partial" in event_types
    assert "turn_failed" not in event_types
    complete = [payload for typ, payload in events if typ == "complete"][-1]
    assert complete["status"] == "partial"
    assert complete["failed_agents"] == ["claude"]
    agent_error = [payload for typ, payload in events if typ == "agent_error"][0]
    assert agent_error["retryable"] is True
    assert agent_error["attempts"] == 1


def test_room_turn_all_failed_is_failed_once(monkeypatch, tmp_path):
    from agent_lab import room

    events: list[tuple[str, dict]] = []

    def fake_call_agent(agent, _system, _user, **_kwargs):
        raise RuntimeError(f"{agent} timed out")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    folder, _messages, _plan_md = room.run_room(
        "Please discuss retry behavior.",
        agents=["cursor", "claude"],
        synthesize=False,
        parallel_rounds=1,
        sessions_base=tmp_path,
        on_event=lambda typ, payload: events.append((typ, payload)),
    )

    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["status"] == "failed"
    assert run["last_turn"]["failed_agents"] == ["claude", "cursor"]
    assert run["last_turn"].get("succeeded_agents") is None
    turn_failed_events = [payload for typ, payload in events if typ == "turn_failed"]
    assert len(turn_failed_events) == 1
    assert turn_failed_events[0]["failed_agents"] == ["claude", "cursor"]
