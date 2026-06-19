"""G005 — consensus gate: Room consensus gates DISCUSS->PLAN_GATE (plan.md) under the pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab import consensus_gate


def _write(folder: Path, run: dict) -> None:
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")


def test_consensus_gate_met_signals() -> None:
    assert consensus_gate.consensus_gate_met({"consensus": {"status": "reached"}}) is True
    assert consensus_gate.consensus_gate_met({"consensus": {"endorse_count": 2}}) is True
    assert consensus_gate.consensus_gate_met({"consensus": {"endorse_count": 1}}) is False
    assert consensus_gate.consensus_gate_met({}) is False
    assert consensus_gate.consensus_gate_met({"mission_loop": {"consensus": {"status": "reached"}}}) is True


def test_discuss_gates_on_consensus_when_flag_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mission_advance import maybe_advance_mission
    from agent_lab.run_meta import read_run_meta

    # No consensus signal => plan.md stays gated at DISCUSS.
    _write(tmp_path, {"mission_loop": {"enabled": True, "phase": "DISCUSS", "autonomous_segment": {"active": True}}})
    out = maybe_advance_mission(tmp_path, scheduled=True)
    assert read_run_meta(tmp_path)["mission_loop"]["phase"] == "DISCUSS"
    assert out.get("reason") == "consensus_pending"


def test_discuss_advances_when_consensus_reached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mission_advance import maybe_advance_mission
    from agent_lab.run_meta import read_run_meta

    _write(
        tmp_path,
        {
            "mission_loop": {"enabled": True, "phase": "DISCUSS", "autonomous_segment": {"active": True}},
            "consensus": {"status": "reached"},
        },
    )
    maybe_advance_mission(tmp_path, scheduled=True)
    assert read_run_meta(tmp_path)["mission_loop"]["phase"] == "PLAN_GATE"


def test_discuss_advances_when_flag_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # G006 default-on: explicit opt-out required to test legacy behavior
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "0")
    from agent_lab.mission_advance import maybe_advance_mission
    from agent_lab.run_meta import read_run_meta

    # OFF-parity: no consensus signal, flag off => advances as before.
    _write(tmp_path, {"mission_loop": {"enabled": True, "phase": "DISCUSS", "autonomous_segment": {"active": True}}})
    maybe_advance_mission(tmp_path, scheduled=True)
    assert read_run_meta(tmp_path)["mission_loop"]["phase"] == "PLAN_GATE"


def test_consensus_gate_is_read_only() -> None:
    # Room debate preserved: gate does not mutate consensus state.
    run = {"consensus": {"status": "incomplete", "endorse_count": 1}}
    consensus_gate.consensus_gate_met(run)
    assert run["consensus"] == {"status": "incomplete", "endorse_count": 1}
