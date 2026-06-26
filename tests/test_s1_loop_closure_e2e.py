"""S1 Phase A — loop-closure E2E: a real mock room turn persists turn_metrics
and appends to the cross-session outcome ledger when flags are on."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_mocks import patch_call_agent_reply


def _envelope_reply(act: str, body: str) -> str:
    env = json.dumps({"act": act, "refs": [], "confidence": 0.9})
    return f"```agent-envelope\n{env}\n```\n{body}"


def _fake_call_agent(per_agent: dict[str, int]):
    def call(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "Use src/auth.py JWT middleware.")
        return _envelope_reply("ENDORSE", "Agreed.")

    return call


def test_turn_writes_metrics_and_ledger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agent_lab import room

    monkeypatch.setenv("AGENT_LAB_TURN_METRICS", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr("agent_lab.workspace_roots.project_root", lambda: root)

    patch_call_agent_reply(monkeypatch, _fake_call_agent({}))

    folder, _messages, _plan = room.run_room(
        "JWT path in src/auth.py — pick retry strategy.",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
    )

    # (1) turn_metrics persisted into the turn
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    metrics = run["turns"][0].get("turn_metrics")
    assert metrics is not None, "turn_metrics not persisted"
    assert metrics["schema_version"] == 1
    assert metrics["agents"], "agents roster not captured"
    assert "oracle_rollup" in metrics

    # (2) one outcome row appended to the cross-session ledger
    ledger = root / ".agent-lab" / "outcomes.jsonl"
    assert ledger.is_file(), "outcomes.jsonl not written"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["session_id"] == folder.name
    assert rows[0]["topic_hash"].startswith("sha1:")


def test_flags_off_is_inert(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agent_lab import room

    monkeypatch.delenv("AGENT_LAB_TURN_METRICS", raising=False)
    monkeypatch.delenv("AGENT_LAB_OUTCOME_LEDGER", raising=False)
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr("agent_lab.workspace_roots.project_root", lambda: root)

    patch_call_agent_reply(monkeypatch, _fake_call_agent({}))

    folder, _messages, _plan = room.run_room(
        "Pick a retry strategy.",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
    )

    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert "turn_metrics" not in run["turns"][0]
    assert not (root / ".agent-lab" / "outcomes.jsonl").exists()
