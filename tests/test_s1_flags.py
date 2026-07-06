"""S1 flag resolution — supervisor preset implicit ON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.outcome_harvester import record_turn_outcome
from agent_lab.s1_flags import s1_flag_enabled


def test_s1_flags_supervisor_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_TURN_METRICS", raising=False)
    monkeypatch.delenv("AGENT_LAB_OUTCOME_LEDGER", raising=False)
    monkeypatch.delenv("AGENT_LAB_FEEDBACK_ADVISOR", raising=False)
    assert s1_flag_enabled("AGENT_LAB_TURN_METRICS", room_preset="supervisor")
    assert s1_flag_enabled("AGENT_LAB_OUTCOME_LEDGER", run_meta={"room_preset": "supervisor"})
    assert s1_flag_enabled("AGENT_LAB_FEEDBACK_ADVISOR", room_preset="supervisor")


def test_s1_flags_fast_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_TURN_METRICS", raising=False)
    assert not s1_flag_enabled("AGENT_LAB_TURN_METRICS", room_preset="fast")


def test_s1_flags_explicit_off_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_METRICS", "0")
    assert not s1_flag_enabled("AGENT_LAB_TURN_METRICS", room_preset="supervisor")


def test_record_turn_outcome_supervisor_implicit_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "sess-supervisor"
    folder.mkdir()
    run = {
        "topic": "JWT middleware in src/auth.py",
        "room_preset": "supervisor",
        "turns": [
            {
                "category": {"value": "standard", "source": "classifier"},
                "roles": {"cursor": "executor"},
                "agents_used": ["cursor", "codex"],
            }
        ],
        "objections": [],
        "executions": [],
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))
    monkeypatch.delenv("AGENT_LAB_TURN_METRICS", raising=False)
    monkeypatch.delenv("AGENT_LAB_OUTCOME_LEDGER", raising=False)

    record_turn_outcome(folder, 1)

    after = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert after["turns"][-1].get("turn_metrics") is not None
