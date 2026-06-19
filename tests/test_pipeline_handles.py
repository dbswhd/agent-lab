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
    assert res["ok"] and res["pipeline"] == "off"


def test_pipeline_handle_requires_session() -> None:
    from agent_lab.slash_commands import dispatch

    res = dispatch("/pipeline status", session_folder=None)
    assert res["ok"] is False
    assert "no active session" in res["error"]


def test_clarify_handle_sets_phase(tmp_path: Path) -> None:
    from agent_lab.run_meta import read_run_meta
    from agent_lab.slash_commands import dispatch

    _write_run(tmp_path, {"enabled": True, "phase": "DISCUSS"})
    res = dispatch("/clarify", session_folder=tmp_path)
    assert res["ok"] and res["phase"] == "CLARIFY"
    assert read_run_meta(tmp_path)["mission_loop"]["phase"] == "CLARIFY"


def test_plan_handle_sets_phase(tmp_path: Path) -> None:
    from agent_lab.run_meta import read_run_meta
    from agent_lab.slash_commands import dispatch

    _write_run(tmp_path, {"enabled": True, "phase": "CLARIFY"})
    res = dispatch("/plan", session_folder=tmp_path)
    assert res["ok"] and res["phase"] == "DISCUSS"
    assert read_run_meta(tmp_path)["mission_loop"]["phase"] == "DISCUSS"


# --- catalog registration ------------------------------------------------------


def test_catalog_lists_pipeline_handles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "1")
    from agent_lab.command_registry import list_commands

    catalog = list_commands(session_folder=tmp_path, workspace=tmp_path)
    by_id = {c["id"]: c for c in catalog["commands"]}
    for cid in ("pipeline", "clarify", "plan"):
        assert cid in by_id, cid
        assert by_id[cid]["enabled"] is True


def test_catalog_gates_clarify_plan_when_pipeline_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "0")
    from agent_lab.command_registry import list_commands

    catalog = list_commands(session_folder=tmp_path, workspace=tmp_path)
    by_id = {c["id"]: c for c in catalog["commands"]}
    # /pipeline stays available to turn it back on
    assert by_id["pipeline"]["enabled"] is True
    # /clarify and /plan disabled when explicitly off
    assert by_id["clarify"]["enabled"] is False
    assert by_id["plan"]["enabled"] is False
    assert by_id["clarify"]["disabled_reason"] == "pipeline_disabled"


def test_execute_command_routes_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "1")
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
