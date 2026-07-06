"""Tests for agent_lab.run.state — F11 Stage 1."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.run.meta import patch_run_meta, read_run_meta, stamp_run_meta, write_run_meta
from agent_lab.run.schema import RuntimeValidationError, validate_run
from agent_lab.run.state import RunState


def test_run_state_from_raw_validates_mission_phase() -> None:
    with pytest.raises(RuntimeValidationError, match="invalid mission_loop.phase"):
        RunState.from_raw({"mission_loop": {"phase": "NOT_A_PHASE"}})


def test_run_state_from_raw_accepts_empty() -> None:
    state = RunState.from_raw({})
    assert isinstance(state, RunState)
    assert isinstance(state, dict)
    assert state == {}


def test_validate_run_delegates_to_run_state() -> None:
    with pytest.raises(RuntimeValidationError, match="invalid execution status"):
        validate_run({"executions": [{"status": "bogus"}]})


def test_read_run_meta_returns_run_state(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {"workflow_id": "test.read", "mission_loop": {"phase": "DISCUSS"}})

    run = read_run_meta(folder)
    assert isinstance(run, RunState)
    assert run.get("workflow_id") == "test.read"
    assert run.get("mission_loop", {}).get("phase") == "DISCUSS"


def test_read_run_meta_missing_file_is_empty_run_state(tmp_path: Path) -> None:
    run = read_run_meta(tmp_path)
    assert isinstance(run, RunState)
    assert run == {}


def test_patch_run_meta_updater_receives_run_state(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {"workflow_id": "test.patch"})

    seen: list[type] = []

    def _touch(run: RunState) -> RunState:
        seen.append(type(run))
        run["touched"] = True
        return run

    updated = patch_run_meta(folder, _touch)
    assert seen == [RunState]
    assert isinstance(updated, RunState)
    assert read_run_meta(folder).get("touched") is True


def test_stamp_run_meta_accepts_run_state() -> None:
    run = RunState.from_memory({"workflow_id": "test.stamp"})
    updated = stamp_run_meta(run, topic="hello")
    assert isinstance(updated, RunState)
    assert updated.get("topic") == "hello"
    assert updated is run


def test_run_state_from_memory_skips_validation() -> None:
    state = RunState.from_memory({"executions": [{"status": "not_yet_validated"}]})
    assert isinstance(state, RunState)
    assert state.get("executions")[0]["status"] == "not_yet_validated"


def test_session_context_returns_run_state(tmp_path: Path) -> None:
    from agent_lab.room.session_persist import _session_context

    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {"workflow_id": "test.ctx"})
    plan_md, run = _session_context(folder)
    assert plan_md == ""
    assert isinstance(run, RunState)
    assert run.get("workflow_id") == "test.ctx"


def test_plan_workflow_phase_accepts_run_state(tmp_path: Path) -> None:
    from agent_lab.plan.workflow_state import get_plan_workflow, plan_workflow_phase

    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(
        folder,
        {
            "plan_workflow": {"enabled": True, "phase": "DRAFT"},
        },
    )
    run = read_run_meta(folder)
    assert plan_workflow_phase(run) == "DRAFT"
    assert get_plan_workflow(run).get("enabled") is True


def test_run_state_supports_dict_spread_in_patch(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {"completed_steps": []})

    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "completed_steps": [{"step": "turn_1_round_1_cursor", "agent": "cursor"}],
        },
    )

    run = read_run_meta(folder)
    assert len(run.get("completed_steps") or []) == 1
