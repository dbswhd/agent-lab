"""§1 — pipeline manual handles (/pipeline status, /clarify, /plan),
catalog registration, and the formalized CLARIFY transition rows (AC7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_run(folder: Path, ml: dict) -> None:
    (folder / "run.json").write_text(json.dumps({"mission_loop": ml}), encoding="utf-8")


# --- slash handlers ------------------------------------------------------------


def test_pipeline_handle_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "1")
    from agent_lab.slash_commands import dispatch

    _write_run(tmp_path, {"enabled": True, "phase": "DISCUSS"})
    res = dispatch("/pipeline", session_folder=tmp_path)
    assert res["ok"]
    assert res["pipeline"] == "on"
    assert res["phase"] == "DISCUSS"
    assert res["mode"] == "CONSENSUS"


def test_pipeline_status_reflects_env_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "0")
    from agent_lab.slash_commands import dispatch

    _write_run(tmp_path, {"enabled": True, "phase": "DISCUSS"})
    res = dispatch("/pipeline", session_folder=tmp_path)
    assert res["ok"] and res["pipeline"] == "on"


def test_pipeline_handle_requires_session() -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/pipeline status", session_folder=None)
    assert res["ok"] is False
    assert "no active session" in res["error"]


def test_clarify_handle_sets_phase(tmp_path: Path) -> None:
    from agent_lab.run.meta import read_run_meta
    from agent_lab.slash_commands import dispatch

    _write_run(tmp_path, {"enabled": True, "phase": "DISCUSS"})
    res = dispatch("/clarify", session_folder=tmp_path)
    assert res["ok"] and res["phase"] == "CLARIFY"
    assert read_run_meta(tmp_path)["mission_loop"]["phase"] == "CLARIFY"


def test_plan_handle_sets_phase(tmp_path: Path) -> None:
    from agent_lab.run.meta import read_run_meta
    from agent_lab.slash_commands import dispatch

    _write_run(tmp_path, {"enabled": True, "phase": "CLARIFY"})
    res = dispatch("/plan", session_folder=tmp_path)
    assert res["ok"] and res["phase"] == "DISCUSS"
    assert read_run_meta(tmp_path)["mission_loop"]["phase"] == "DISCUSS"


def test_plan_handle_without_execute_arg_leaves_mission_loop_disabled(tmp_path: Path) -> None:
    from agent_lab.run.meta import read_run_meta
    from agent_lab.slash_commands import dispatch

    _write_run(tmp_path, {"enabled": False, "phase": "CLARIFY"})
    res = dispatch("/plan", session_folder=tmp_path)
    assert res["ok"] and "execute_intent" not in res
    assert read_run_meta(tmp_path)["mission_loop"]["enabled"] is False


def test_plan_execute_handle_enables_mission_loop_immediately(tmp_path: Path) -> None:
    """P1-2: '/plan execute' captures the human's execute intent at plan-entry
    time instead of requiring a separate later /execute discovery step."""
    from agent_lab.run.meta import read_run_meta
    from agent_lab.slash_commands import dispatch

    _write_run(tmp_path, {"enabled": False, "phase": "CLARIFY"})
    res = dispatch("/plan execute", session_folder=tmp_path)
    assert res["ok"] and res["phase"] == "DISCUSS"
    assert res["execute_intent"] is True
    assert read_run_meta(tmp_path)["mission_loop"]["enabled"] is True


_GOOD_PLAN = """# Plan

## 지금 실행

1. Fix auth module
   - 무엇을: JWT validation in `src/auth.py`
   - 어디서: `src/auth.py`
   - 검증: `make test tests/test_auth.py`
"""

_BAD_PLAN = """# Plan

## 지금 실행

1. Fix something
   - 무엇을: fix
   - 어디서: somewhere
   - 검증: ok
"""


def test_execute_handle_requires_session() -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/execute", session_folder=None)
    assert res["ok"] is False
    assert "no active session" in res["error"]


def test_execute_handle_requires_plan_md(tmp_path: Path) -> None:
    from agent_lab.slash_commands import dispatch

    _write_run(tmp_path, {"enabled": False, "phase": "DISCUSS"})
    res = dispatch("/execute", session_folder=tmp_path)
    assert res["ok"] is False
    assert "plan.md" in res["error"]


def test_execute_handle_auto_enables_mission_loop_and_enqueues(tmp_path: Path) -> None:
    """/execute is the explicit human action for the L0 'diff' half — it must
    not require the human to already know about mission_loop.enabled or the
    Autonomy dial (docs/NORTH-STAR.md L0/L1 ladder)."""
    from agent_lab.run.meta import read_run_meta
    from agent_lab.slash_commands import dispatch

    _write_run(tmp_path, {"enabled": False, "phase": "DISCUSS"})
    (tmp_path / "plan.md").write_text(_GOOD_PLAN, encoding="utf-8")

    res = dispatch("/execute", session_folder=tmp_path)
    assert res["ok"] is True
    assert res["status"] == "ok"
    assert res["phase"] == "EXECUTE_QUEUE"

    ml = read_run_meta(tmp_path)["mission_loop"]
    assert ml["enabled"] is True
    assert ml["phase"] == "EXECUTE_QUEUE"
    assert ml["pending_action_indices"] == [1]


def test_execute_handle_reports_reject_without_crashing(tmp_path: Path) -> None:
    from agent_lab.slash_commands import dispatch

    _write_run(tmp_path, {"enabled": False, "phase": "DISCUSS"})
    (tmp_path / "plan.md").write_text(_BAD_PLAN, encoding="utf-8")

    res = dispatch("/execute", session_folder=tmp_path)
    assert res["ok"] is True
    assert res["status"] == "reject"
    assert res["phase"] == "DISCUSS"


# --- catalog registration ------------------------------------------------------


def test_catalog_lists_pipeline_handles(tmp_path: Path) -> None:
    from agent_lab.command_registry import list_commands

    catalog = list_commands(session_folder=tmp_path, workspace=tmp_path)
    by_id = {c["id"]: c for c in catalog["commands"]}
    for cid in ("pipeline", "clarify", "plan", "execute"):
        assert cid in by_id, cid
        assert by_id[cid]["enabled"] is True


def test_catalog_pipeline_commands_always_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "0")
    from agent_lab.command_registry import list_commands

    catalog = list_commands(session_folder=tmp_path, workspace=tmp_path)
    by_id = {c["id"]: c for c in catalog["commands"]}
    for cid in ("pipeline", "clarify", "plan", "execute"):
        assert by_id[cid]["enabled"] is True


def test_execute_command_routes_pipeline(tmp_path: Path) -> None:
    from agent_lab.command_registry import execute_command

    _write_run(tmp_path, {"enabled": True, "phase": "DISCUSS"})
    res = execute_command(tmp_path, "pipeline", args="status", workspace=tmp_path)
    assert res["ok"] is True
    assert res["kind"] == "server"
    assert "pipeline on" in res["text"]


# --- transition table (AC7) ----------------------------------------------------


def test_transition_table_has_clarify_rows() -> None:
    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.transitions import TRANSITION_TABLE

    enable_to_clarify = [
        r
        for r in TRANSITION_TABLE
        if r.event == RuntimeEvent.MISSION_ENABLE and r.to_phase == "CLARIFY" and "MISSION_DEFINE" in r.from_phases
    ]
    assert len(enable_to_clarify) == 1
    assert enable_to_clarify[0].guard == "mission_define_ready_pipeline"

    clarify_to_discuss = [
        r
        for r in TRANSITION_TABLE
        if r.event == RuntimeEvent.MISSION_ADVANCE and "CLARIFY" in r.from_phases and r.to_phase == "DISCUSS"
    ]
    assert len(clarify_to_discuss) == 1
    assert clarify_to_discuss[0].guard == "clarity_met"


def test_clarify_enable_and_discuss_edges_have_distinct_guards() -> None:
    """The legacy MISSION_ENABLE→DISCUSS and new →CLARIFY edges must not collide."""
    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.transitions import TRANSITION_TABLE

    enable_rows = [
        r for r in TRANSITION_TABLE if r.event == RuntimeEvent.MISSION_ENABLE and "MISSION_DEFINE" in r.from_phases
    ]
    guards = {r.guard for r in enable_rows}
    to_phases = {r.to_phase for r in enable_rows}
    assert to_phases == {"CLARIFY", "DISCUSS"}
    assert len(guards) == len(enable_rows)  # distinct guards, no exclusive-edge conflict
