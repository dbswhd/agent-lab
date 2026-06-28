"""P4: mock Room discuss turn with kimi_work in roster (CI-safe)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: tmp_path)
    monkeypatch.setenv("KIMI_SHARE_DIR", str(tmp_path / "share"))
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "1")


def _seed_session(folder: Path, *, agents: list[str]) -> None:
    folder.mkdir(parents=True)
    (folder / "topic.txt").write_text("mock kimi_work discuss\n", encoding="utf-8")
    (folder / "plan.md").write_text("# plan\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        json.dumps({"role": "user", "content": "seed", "ts": "t0"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "topic": "mock kimi_work discuss",
                "agents": agents,
                "status": "idle",
                "turns": [],
                "actions": [],
                "approvals": [],
                "executions": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def test_mock_discuss_kimi_work_roster(tmp_path: Path) -> None:
    from agent_lab.room import continue_room_round

    folder = tmp_path / "sess-kimi-work"
    agents = ["kimi_work", "local"]
    _seed_session(folder, agents=agents)

    messages, _plan = continue_room_round(
        folder,
        "[mock-tools] smoke roster",
        agents=agents,
        synthesize=False,
        parallel_rounds=1,
    )
    agent_replies = [m for m in messages if m.role == "agent" and (m.content or "").strip()]
    assert agent_replies, "expected kimi_work/local mock replies"
    assert any(m.agent == "kimi_work" for m in agent_replies)
    assert (folder / "kimi_work.json").is_file()


def test_mock_consensus_kimi_work_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.kimi import work_provider as kwp
    from agent_lab.room.parallel_rounds import run_agent_rounds
    from agent_lab.room.messages import ChatMessage
    from agent_lab.room.session_persist import load_session_messages

    envelope_flags: list[bool] = []
    orig_respond = kwp.respond

    def _wrap_respond(*args: object, **kwargs: object) -> str:
        envelope_flags.append(bool(kwargs.get("request_structured_envelope")))
        return orig_respond(*args, **kwargs)

    monkeypatch.setattr(kwp, "respond", _wrap_respond)
    monkeypatch.setattr("agent_lab.agents.registry.kimi_work_provider.respond", _wrap_respond)
    monkeypatch.setenv("AGENT_LAB_STRUCTURED_ENVELOPE", "1")

    folder = tmp_path / "sess-kimi-consensus"
    agents = ["kimi_work", "cursor", "codex"]
    _seed_session(folder, agents=agents)

    topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
    messages = load_session_messages(folder)
    messages.append(
        ChatMessage(
            role="user",
            agent=None,
            content="Pick JWT middleware path — consensus check.",
        )
    )
    run_meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    run_meta["_active_consensus"] = True
    run_meta["_session_id"] = folder.name
    run_meta["_session_folder"] = str(folder.resolve())

    replies = run_agent_rounds(
        topic,
        messages,
        agents=agents,
        parallel_rounds=2,
        run_meta=run_meta,
    )
    kimi_msgs = [
        m
        for m in replies
        if m.role == "agent" and m.agent == "kimi_work" and (m.content or "").strip()
    ]
    assert kimi_msgs, "expected kimi_work consensus reply"
    assert any(envelope_flags), "expected structured envelope on kimi_work R2+ consensus turn"
    assert "Kimi Work" in kimi_msgs[-1].content
