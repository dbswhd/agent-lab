"""CENT-durable: completed_steps persistence and resume skip."""

from __future__ import annotations

import json


from agent_mocks import patch_call_agent_reply


def test_completed_step_key_and_record(tmp_path):
    from agent_lab.run.meta import (
        completed_step_key,
        get_completed_step,
        record_completed_step,
        read_run_meta,
    )

    folder = tmp_path / "sess"
    folder.mkdir()
    key = completed_step_key(human_turn=2, parallel_round=1, agent="cursor")
    assert key == "turn_2_round_1_cursor"

    record_completed_step(
        folder,
        human_turn=2,
        parallel_round=1,
        agent="cursor",
        content="cached reply",
        envelope={"act": "PROPOSE"},
    )
    run = read_run_meta(folder)
    step = get_completed_step(run, human_turn=2, parallel_round=1, agent="cursor")
    assert step is not None
    assert step["content"] == "cached reply"
    assert step["step"] == key


def test_clear_completed_steps_for_human_turn(tmp_path):
    from agent_lab.run.meta import (
        clear_completed_steps_for_human_turn,
        read_run_meta,
        record_completed_step,
    )

    folder = tmp_path / "sess"
    folder.mkdir()
    record_completed_step(
        folder,
        human_turn=1,
        parallel_round=1,
        agent="cursor",
        content="a",
    )
    record_completed_step(
        folder,
        human_turn=2,
        parallel_round=1,
        agent="codex",
        content="b",
    )
    clear_completed_steps_for_human_turn(folder, 1)
    run = read_run_meta(folder)
    steps = run.get("completed_steps") or []
    assert len(steps) == 1
    assert steps[0]["human_turn"] == 2


def test_run_parallel_round_skips_completed_agent(monkeypatch, tmp_path):
    from agent_lab import room
    from agent_lab.run.meta import record_completed_step, write_run_meta

    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("topic\n")
    write_run_meta(folder, {"agents": ["cursor", "claude"]})
    record_completed_step(
        folder,
        human_turn=1,
        parallel_round=1,
        agent="cursor",
        content="cursor cached ok",
    )

    calls: list[str] = []

    def fake_call_agent(agent, _system, _user, **_kwargs):
        calls.append(agent)
        return f"{agent} live ok"

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    run_meta = {
        "_session_folder": str(folder),
        "_active_turn_mode": "discuss",
        "_active_synthesize": False,
        "_active_consensus": False,
    }
    messages = [room.ChatMessage(role="user", agent=None, content="hello")]
    replies = room.run_parallel_round(
        "topic",
        messages,
        agents=["cursor", "claude"],
        parallel_round=1,
        run_meta=run_meta,
        human_turn_index=0,
    )
    assert calls == ["claude"]
    agents = [m.agent for m in replies if m.role == "agent"]
    assert "cursor" in agents
    assert "claude" in agents
    assert any(m.content == "cursor cached ok" for m in replies)


def test_call_one_agent_records_completed_step(monkeypatch, tmp_path):
    from agent_lab import room
    from agent_lab.run.meta import get_completed_step, read_run_meta, write_run_meta

    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {})

    patch_call_agent_reply(
        monkeypatch,
        lambda *_a, **_k: '```agent-envelope\n{"act":"PROPOSE"}\n```\ncursor ok',
    )
    monkeypatch.setattr(room, "model_label", lambda agent: agent)
    monkeypatch.setattr(
        room,
        "build_agent_context_bundle",
        lambda *a, **k: type(
            "B",
            (),
            {
                "render": lambda self: "payload",
                "meta": type("M", (), {"to_dict": lambda self: {}})(),
            },
        )(),
    )

    run_meta = {"_session_folder": str(folder)}
    msg = room._call_one_agent(
        "cursor",
        topic="t",
        thread=[],
        parallel_round=1,
        permissions=None,
        review_mode=False,
        review_advocate=None,
        plan_md="",
        run_meta=run_meta,
        on_event=None,
        human_turn_index=0,
    )
    assert msg.role == "agent"
    step = get_completed_step(read_run_meta(folder), human_turn=1, parallel_round=1, agent="cursor")
    assert step is not None
    assert "cursor ok" in step["content"]


def test_durable_regression_fixture_shape():
    fixture = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "sessions"
        / "_regression"
        / "durable_completed_steps"
    )
    run_path = fixture / "run.json"
    assert run_path.is_file()
    run = json.loads(run_path.read_text(encoding="utf-8"))
    steps = run.get("completed_steps") or []
    assert len(steps) >= 1
    assert steps[0].get("step", "").startswith("turn_")
