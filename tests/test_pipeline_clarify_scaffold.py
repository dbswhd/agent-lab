"""G001/G002 — AGENT_LAB_PIPELINE flag, CLARIFY phase, and clarity-gated advance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_run(folder: Path, ml: dict, *, goal_text: str | None = None) -> None:
    run: dict = {"mission_loop": ml}
    if goal_text is not None:
        run["verified_loop"] = {"loop_goal": {"text": goal_text}}
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")


def test_pipeline_enabled_env_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.mission_loop import pipeline_enabled, pipeline_explicitly_disabled

    # G006 default-on: unset enables pipeline
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
    assert pipeline_enabled() is True
    assert pipeline_explicitly_disabled() is False

    monkeypatch.setenv("AGENT_LAB_PIPELINE", "1")
    assert pipeline_enabled() is True
    assert pipeline_explicitly_disabled() is False

    for off in ("0", "false", "no", "off"):
        monkeypatch.setenv("AGENT_LAB_PIPELINE", off)
        assert pipeline_enabled() is False, off
        assert pipeline_explicitly_disabled() is True, off


def test_clarify_in_phase_vocab() -> None:
    from agent_lab.run_schema import _VALID_MISSION_PHASES
    from agent_lab.runtime.phases import MISSION_PHASES

    assert "CLARIFY" in MISSION_PHASES
    assert "CLARIFY" in _VALID_MISSION_PHASES


def test_clarify_advances_when_anchored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mission_advance import maybe_advance_mission
    from agent_lab.run_meta import read_run_meta

    _write_run(
        tmp_path,
        {"enabled": True, "phase": "CLARIFY", "autonomous_segment": {"active": True}},
        goal_text="fix the null check in src/agent_lab/run_meta.py",
    )
    maybe_advance_mission(tmp_path, scheduled=True)
    ml = read_run_meta(tmp_path).get("mission_loop", {})
    assert ml.get("phase") == "DISCUSS"


def test_clarify_stays_when_vague(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mission_advance import maybe_advance_mission
    from agent_lab.run_meta import read_run_meta

    _write_run(
        tmp_path,
        {"enabled": True, "phase": "CLARIFY", "autonomous_segment": {"active": True}},
        goal_text="make the app better",
    )
    out = maybe_advance_mission(tmp_path, scheduled=True)
    ml = read_run_meta(tmp_path).get("mission_loop", {})
    assert ml.get("phase") == "CLARIFY", out
    assert out.get("reason") == "clarity_pending"


def test_clarify_branch_refuses_when_flag_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # G006: legacy behavior requires explicit opt-out
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "0")
    from agent_lab.mission_advance import maybe_advance_mission
    from agent_lab.run_meta import read_run_meta

    _write_run(
        tmp_path,
        {"enabled": True, "phase": "CLARIFY", "autonomous_segment": {"active": True}},
        goal_text="make the app better",
    )
    out = maybe_advance_mission(tmp_path, scheduled=True)
    ml = read_run_meta(tmp_path).get("mission_loop", {})
    assert ml.get("phase") == "CLARIFY", out
    assert out.get("reason") == "pipeline_disabled"


def test_clarify_branch_default_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With default-on, an anchored goal advances from CLARIFY even when env is unset."""
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mission_advance import maybe_advance_mission
    from agent_lab.run_meta import read_run_meta

    _write_run(
        tmp_path,
        {"enabled": True, "phase": "CLARIFY", "autonomous_segment": {"active": True}},
        goal_text="fix the null check in src/agent_lab/run_meta.py",
    )
    maybe_advance_mission(tmp_path, scheduled=True)
    ml = read_run_meta(tmp_path).get("mission_loop", {})
    assert ml.get("phase") == "DISCUSS"
