from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.mission.loop import enable_mission_loop, pause_mission_loop, resume_mission_loop
from agent_lab.mission.advance import on_verify_result
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.runtime.boulder import (
    boulder_state,
    clear_boulder,
    clear_last_failure,
    last_failure,
    record_last_failure,
    sync_boulder_from_partial,
)
from agent_lab.runtime.snapshot import build_runtime_snapshot


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "sess-boulder"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_record_and_clear_last_failure(session_folder: Path) -> None:
    record_last_failure(
        session_folder,
        lane="execute",
        event="execute.verify.fail",
        reason="tests failed",
        phase="REPAIR",
        action_index=1,
        resume_phase="REPAIR",
    )
    run = read_run_meta(session_folder)
    lf = last_failure(run)
    assert lf is not None
    assert lf["event"] == "execute.verify.fail"
    assert lf["reason"] == "tests failed"
    clear_last_failure(session_folder)
    assert last_failure(read_run_meta(session_folder)) is None


def test_pause_syncs_boulder_and_snapshot(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _dry(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update({"phase": "DRY_RUN", "current_action_index": 1})
        return run

    patch_run_meta(session_folder, _dry)
    pause_mission_loop(session_folder, reason="test_stop", cleanup_executions=False)

    run = read_run_meta(session_folder)
    b = boulder_state(run)
    assert b is not None
    assert b["resume_phase"] == "EXECUTE_QUEUE"
    assert b["source"] == "pause"

    snap = build_runtime_snapshot(session_folder)
    assert snap["mission"]["paused"] is True
    assert snap["boulder"]["resume_phase"] == "EXECUTE_QUEUE"
    assert snap["last_failure"]["event"] == "mission.pause"


def test_resume_clears_boulder_and_failure(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    pause_mission_loop(session_folder, reason="test_stop", cleanup_executions=False)
    resume_mission_loop(session_folder)

    run = read_run_meta(session_folder)
    assert run.get("runtime", {}).get("boulder") is None
    assert boulder_state(run) is None
    assert last_failure(run) is None


def test_verify_fail_records_last_failure(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _verify(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "phase": "VERIFY",
                "current_action_index": 1,
                "last_execution_id": "exec-1",
                "pending_action_indices": [1],
            }
        )
        return run

    patch_run_meta(session_folder, _verify)
    on_verify_result(
        session_folder,
        action_index=1,
        verdict="fail",
        reason="AUTH_OK missing",
    )
    lf = last_failure(read_run_meta(session_folder))
    assert lf is not None
    assert lf["event"] == "execute.verify.fail"
    assert lf["resume_phase"] == "REPAIR"


def test_verify_pass_clears_last_failure(session_folder: Path) -> None:
    record_last_failure(
        session_folder,
        lane="execute",
        event="execute.verify.fail",
        reason="stale",
        phase="REPAIR",
        action_index=1,
    )
    enable_mission_loop(session_folder)

    def _ready(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "phase": "VERIFY",
                "pending_action_indices": [],
                "current_action_index": 1,
            }
        )
        return run

    patch_run_meta(session_folder, _ready)
    on_verify_result(session_folder, action_index=1, verdict="pass", reason="ok")
    assert last_failure(read_run_meta(session_folder)) is None


def test_sync_boulder_from_partial_fallback(session_folder: Path) -> None:
    def _partial(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml["last_partial"] = {
            "phase": "MERGE_REVIEW",
            "resume_phase": "EXECUTE_QUEUE",
            "action_index": 2,
            "at": "2026-01-01T00:00:00+00:00",
            "reason": "legacy",
        }
        return run

    def _paused(run: dict) -> dict:
        run = _partial(run)
        run["mission_loop"]["phase"] = "MISSION_PAUSED"
        return run

    patch_run_meta(session_folder, _paused)
    assert boulder_state(read_run_meta(session_folder))["resume_phase"] == "EXECUTE_QUEUE"

    sync_boulder_from_partial(session_folder, source="pause")
    run = read_run_meta(session_folder)
    assert run["runtime"]["boulder"]["source"] == "pause"
    clear_boulder(session_folder)
    assert boulder_state(read_run_meta(session_folder))["source"] == "last_partial"
