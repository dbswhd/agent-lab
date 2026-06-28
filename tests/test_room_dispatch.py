"""Room Dispatch Protocol (CMD-RDP) tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.room.dispatch import (
    dispatch_max_fanout,
    dispatch_run_meta_patch,
    parse_dispatch_from_message,
    parse_delegate_from_message,
)


def test_parse_delegate_unchanged():
    spec = parse_delegate_from_message('DELEGATE codex: "run smoke"')
    assert spec == {"agent": "codex", "prompt": "run smoke"}


def test_parse_parallel_dispatch():
    spec = parse_dispatch_from_message('DISPATCH parallel: codex,cursor: "survey hooks"')
    assert spec is not None
    assert spec.op == "parallel_delegate"
    assert spec.agents == ("codex", "cursor")
    assert spec.prompt == "survey hooks"


def test_parallel_dispatch_trims_fanout(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_DISPATCH_MAX_FANOUT", "2")
    assert dispatch_max_fanout() == 2
    spec = parse_dispatch_from_message('DISPATCH parallel: codex,cursor,claude: "big survey"')
    assert spec is not None
    assert spec.agents == ("codex", "cursor")
    assert spec.trimmed_agents == ("claude",)


def test_delegate_replay_invokes_one_agent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from agent_mocks import patch_call_agent_reply

    from agent_lab import room

    folder = tmp_path / "dispatch-single"
    folder.mkdir()
    (folder / "topic.txt").write_text("dispatch\n", encoding="utf-8")
    (folder / "plan.md").write_text("## 합의\n\n- x\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        json.dumps({"role": "user", "content": "seed", "ts": "2026-06-10T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "agents": ["cursor", "codex", "claude"],
                "status": "idle",
                "turns": [],
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []
    events: list[tuple[str, dict]] = []

    def fake_call(agent, _s, _u, **_kw):
        calls.append(str(agent))
        return "Delegate body for artifact persistence test."

    patch_call_agent_reply(monkeypatch, fake_call)
    monkeypatch.setenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "0")
    monkeypatch.setattr(room, "model_label", lambda a: f"{a}-m")

    room.continue_room_round(
        folder,
        'DELEGATE codex: "parser smoke"',
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        parallel_rounds=3,
        on_event=lambda t, p: events.append((t, p)),
    )
    assert calls == ["codex"]
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["last_delegate"]["agent"] == "codex"
    ledger = run.get("dispatch_ledger") or []
    assert len(ledger) == 1
    assert ledger[0]["op"] == "single_delegate"
    assert any(t == "dispatch_start" for t, _ in events)
    assert any(t == "delegate_start" for t, _ in events)


def test_parallel_fanout_two_agents(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from agent_mocks import patch_call_agent_reply

    from agent_lab import room

    folder = tmp_path / "dispatch-parallel"
    folder.mkdir()
    (folder / "topic.txt").write_text("dispatch\n", encoding="utf-8")
    (folder / "plan.md").write_text("## 합의\n\n- x\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        json.dumps({"role": "user", "content": "seed", "ts": "2026-06-10T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "agents": ["cursor", "codex", "claude"],
                "status": "idle",
                "turns": [],
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    def fake_call(agent, _s, _u, **_kw):
        calls.append(str(agent))
        return f"Work from {agent} with enough text for artifact."

    patch_call_agent_reply(monkeypatch, fake_call)
    monkeypatch.setenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "0")
    monkeypatch.setattr(room, "model_label", lambda a: f"{a}-m")

    room.continue_room_round(
        folder,
        'DISPATCH parallel: codex,cursor: "survey modules"',
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        parallel_rounds=3,
    )
    assert sorted(calls) == ["codex", "cursor"]
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    ledger = run.get("dispatch_ledger") or []
    assert len(ledger) == 1
    assert ledger[0]["op"] == "parallel_delegate"
    assert len(ledger[0].get("artifact_ids") or []) == 2


def test_pre_dispatch_hook_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from agent_lab import room
    from agent_lab.room.hooks import clear_hooks_config_cache

    folder = tmp_path / "dispatch-blocked"
    folder.mkdir()
    hooks = tmp_path / "hooks.toml"
    hooks.write_text(
        '[hooks]\npre_dispatch = ["exit 2"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(hooks))
    clear_hooks_config_cache()
    (folder / "topic.txt").write_text("x\n", encoding="utf-8")
    (folder / "plan.md").write_text("## x\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        json.dumps({"role": "user", "content": "s", "ts": "2026-06-10T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    (folder / "run.json").write_text(
        json.dumps({"agents": ["cursor", "codex", "claude"], "turns": []}),
        encoding="utf-8",
    )
    calls: list[str] = []

    def fake_call(agent, _s, _u, **_kw):
        calls.append(str(agent))
        return "should not run"

    from agent_mocks import patch_call_agent_reply

    patch_call_agent_reply(monkeypatch, fake_call)
    monkeypatch.setenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "0")
    monkeypatch.setattr(room, "model_label", lambda a: a)

    room.continue_room_round(
        folder,
        'DELEGATE codex: "blocked task"',
        agents=["cursor", "codex", "claude"],
        synthesize=False,
    )
    assert calls == []
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    ledger = run.get("dispatch_ledger") or []
    assert ledger[-1]["status"] == "blocked"


def test_dispatch_run_meta_patch_includes_ledger():
    patch = dispatch_run_meta_patch(
        {
            "last_delegate": {"agent": "codex"},
            "dispatch_ledger": [{"id": "disp-001"}],
            "hook_runs": [{"event": "pre_dispatch"}],
        }
    )
    assert patch is not None
    assert patch["dispatch_ledger"][0]["id"] == "disp-001"


def test_envelope_dispatch_intent_harvest():
    from agent_lab.agent.envelope import AgentEnvelope
    from agent_lab.room import ChatMessage
    from agent_lab.room.dispatch_intents import harvest_dispatch_intents_from_turn

    run_meta: dict = {}
    msgs = [
        ChatMessage(
            role="agent",
            agent="codex",
            content="please run",
            envelope=AgentEnvelope(
                act="MESSAGE",
                refs=[],
                to="cursor",
                dispatch={"op": "scoped", "prompt": "lint room_hooks.py"},
            ).to_dict(),
        )
    ]
    rows = harvest_dispatch_intents_from_turn(run_meta, msgs, human_turn=1)
    assert len(rows) == 1
    assert rows[0]["to"] == "cursor"
    assert run_meta["dispatch_intents"][0]["status"] == "pending"
