"""G001/G002 — pipeline orchestration, CLARIFY phase, and clarity-gated advance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_run(folder: Path, ml: dict, *, goal_text: str | None = None) -> None:
    run: dict = {"mission_loop": ml}
    if goal_text is not None:
        run["verified_loop"] = {"loop_goal": {"text": goal_text}}
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")


def test_pipeline_always_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.mission.loop import pipeline_enabled, pipeline_explicitly_disabled

    for val in (None, "0", "false", "no", "off", "1"):
        if val is None:
            monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
        else:
            monkeypatch.setenv("AGENT_LAB_PIPELINE", val)
        assert pipeline_enabled() is True
        assert pipeline_explicitly_disabled() is False


def test_clarify_in_phase_vocab() -> None:
    from agent_lab.run.schema import _VALID_MISSION_PHASES
    from agent_lab.runtime.phases import MISSION_PHASES

    assert "CLARIFY" in MISSION_PHASES
    assert "CLARIFY" in _VALID_MISSION_PHASES


def test_clarify_advances_when_anchored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mission.advance import maybe_advance_mission
    from agent_lab.run.meta import read_run_meta

    _write_run(
        tmp_path,
        {"enabled": True, "phase": "CLARIFY", "autonomous_segment": {"active": True}},
        goal_text="fix the null check in src/agent_lab/run_meta.py",
    )
    maybe_advance_mission(tmp_path, scheduled=True)
    ml = read_run_meta(tmp_path).get("mission_loop", {})
    assert ml.get("phase") == "DISCUSS"


def test_clarify_stays_when_vague(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mission.advance import maybe_advance_mission
    from agent_lab.run.meta import read_run_meta

    _write_run(
        tmp_path,
        {"enabled": True, "phase": "CLARIFY", "autonomous_segment": {"active": True}},
        goal_text="make the app better",
    )
    out = maybe_advance_mission(tmp_path, scheduled=True)
    ml = read_run_meta(tmp_path).get("mission_loop", {})
    assert ml.get("phase") == "CLARIFY", out
    assert out.get("reason") == "clarity_pending"


def test_mode_router_enters_clarify_from_discuss_when_vague(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mode_router import apply_mission_mode_route
    from agent_lab.run.meta import read_run_meta

    _write_run(
        tmp_path,
        {"enabled": True, "phase": "DISCUSS", "autonomous_segment": {"active": True}},
        goal_text="make the app better",
    )
    out = apply_mission_mode_route(tmp_path)
    ml = read_run_meta(tmp_path).get("mission_loop", {})
    assert ml.get("phase") == "CLARIFY"
    assert out is not None and out.get("reason") == "clarity_pending"
