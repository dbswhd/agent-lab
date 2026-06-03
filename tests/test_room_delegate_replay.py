"""Mock replay for scoped delegate call-count guarantees (H-P2)."""

from __future__ import annotations

import json
from pathlib import Path


def _seed_session(folder: Path) -> None:
    folder.mkdir(parents=True)
    (folder / "topic.txt").write_text("delegate replay\n", encoding="utf-8")
    (folder / "plan.md").write_text("## 합의\n\n- delegate fixture\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        json.dumps(
            {
                "role": "user",
                "content": "seed",
                "ts": "2026-06-03T00:00:00+00:00",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "plan_format_version": 1,
                "topic": "delegate replay",
                "agents": ["cursor", "codex", "claude"],
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


def test_delegate_codex_replay_invokes_one_agent_and_writes_artifact(
    monkeypatch,
    tmp_path: Path,
):
    from agent_lab import room

    folder = tmp_path / "delegate-session"
    _seed_session(folder)
    calls: list[str] = []
    events: list[tuple[str, dict]] = []

    def fake_call_agent(agent, _system, _user, **_kwargs):
        calls.append(str(agent))
        return "Delegate result body with enough detail to persist as an artifact."

    monkeypatch.setattr(room, "call_agent", fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    messages, _plan = room.continue_room_round(
        folder,
        'DELEGATE codex: "run benchmark parser smoke"',
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        parallel_rounds=1,
        on_event=lambda typ, payload: events.append((typ, payload)),
    )

    assert calls == ["codex"]
    agent_msgs = [m for m in messages if m.role == "agent"]
    assert [m.agent for m in agent_msgs if "Delegate result" in (m.content or "")] == [
        "codex"
    ]

    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["last_delegate"]["agent"] == "codex"
    assert run["last_delegate"]["replaced_full_round"] is True
    artifacts = run["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["kind"] == "delegate"
    assert artifacts[0]["producer"] == "codex"
    assert artifacts[0]["id"] == run["last_delegate"]["artifact_id"]
    assert [typ for typ, _payload in events].count("delegate_start") == 1
    assert [typ for typ, _payload in events].count("delegate_done") == 1
