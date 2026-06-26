"""G003 — autonomous mode router (CLARIFY/CONSENSUS/EXECUTE) recorded to run.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab import mode_router


def test_select_mode_by_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    assert mode_router.select_mode({"mission_loop": {"phase": "DRY_RUN"}}) == "EXECUTE"
    assert mode_router.select_mode({"mission_loop": {"phase": "VERIFY"}}) == "EXECUTE"
    assert mode_router.select_mode({"mission_loop": {"phase": "DISCUSS"}}) == "CONSENSUS"
    assert mode_router.select_mode({"mission_loop": {"phase": "PLAN_GATE"}}) == "CONSENSUS"


def test_select_mode_clarify_by_clarity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    anchored = {"mission_loop": {"phase": "CLARIFY"}, "verified_loop": {"loop_goal": {"text": "fix src/foo.py"}}}
    vague = {"mission_loop": {"phase": "CLARIFY"}, "verified_loop": {"loop_goal": {"text": "make it better"}}}
    assert mode_router.select_mode(anchored) == "CONSENSUS"
    assert mode_router.select_mode(vague) == "CLARIFY"


def test_record_mode_route_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.run_meta import read_run_meta

    (tmp_path / "run.json").write_text(json.dumps({"mission_loop": {"phase": "DISCUSS"}}), encoding="utf-8")
    route = mode_router.record_mode_route(tmp_path)
    assert route["mode"] == "CONSENSUS"
    persisted = read_run_meta(tmp_path).get("mission_loop", {}).get("mode_route", {})
    assert persisted.get("mode") == "CONSENSUS"
    assert persisted.get("phase") == "DISCUSS"
    assert persisted.get("at")


def test_apply_mission_mode_route_forwards_discuss_to_plan_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mode_router import apply_mission_mode_route
    from agent_lab.run_meta import read_run_meta

    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "mission_loop": {"enabled": True, "phase": "DISCUSS", "autonomous_segment": {"active": True}},
                "consensus": {"status": "reached"},
                "verified_loop": {"loop_goal": {"text": "fix JWT validation in src/auth.py"}},
            }
        ),
        encoding="utf-8",
    )
    out = apply_mission_mode_route(tmp_path)
    assert out is not None and out.get("status") == "forwarded"
    assert read_run_meta(tmp_path)["mission_loop"]["phase"] == "PLAN_GATE"


def test_maybe_advance_records_route_when_flag_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mission_advance import maybe_advance_mission
    from agent_lab.run_meta import read_run_meta

    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "mission_loop": {"enabled": True, "phase": "CLARIFY", "autonomous_segment": {"active": True}},
                "verified_loop": {"loop_goal": {"text": "make it better"}},
            }
        ),
        encoding="utf-8",
    )
    maybe_advance_mission(tmp_path, scheduled=True)
    route = read_run_meta(tmp_path).get("mission_loop", {}).get("mode_route", {})
    assert route.get("mode") == "CLARIFY"  # vague + CLARIFY phase


def test_maybe_advance_always_records_mode_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mission_advance import maybe_advance_mission
    from agent_lab.run_meta import read_run_meta

    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "mission_loop": {"enabled": True, "phase": "DISCUSS", "autonomous_segment": {"active": True}},
                "verified_loop": {"loop_goal": {"text": "fix JWT validation in src/auth.py"}},
            }
        ),
        encoding="utf-8",
    )
    maybe_advance_mission(tmp_path, scheduled=True)
    ml = read_run_meta(tmp_path).get("mission_loop", {})
    assert isinstance(ml.get("mode_route"), dict)
    assert ml["mode_route"].get("mode") == "CONSENSUS"
