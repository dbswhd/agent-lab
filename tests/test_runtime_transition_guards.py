from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.mission.loop import enable_mission_loop, get_mission_loop
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.runtime import dispatch
from agent_lab.runtime.transitions import transition_entry_reason, transition_guard_satisfied


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    folder = tmp_path / "sess-guards"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_mission_enable_blocked_without_define_ready(session_folder: Path) -> None:
    run = read_run_meta(session_folder)
    allowed, reason, phase, rows = transition_entry_reason(run, RuntimeEvent.MISSION_ENABLE)
    assert allowed is False
    assert reason == "guard_blocked"
    assert phase == "MISSION_DEFINE"
    assert rows == ()


def test_mission_enable_allowed_when_define_ready(session_folder: Path) -> None:
    def _ready(run: dict) -> dict:
        run["verified_loop"] = {
            "status": "running",
            "loop_goal": {"text": "fix src/agent_lab/room.py"},
        }
        return run

    patch_run_meta(session_folder, _ready)
    run = read_run_meta(session_folder)
    allowed, reason, phase, rows = transition_entry_reason(run, RuntimeEvent.MISSION_ENABLE)
    assert allowed is True
    assert reason == "mission_enable"
    assert phase == "MISSION_DEFINE"
    assert len(rows) == 1


def test_mission_advance_clarify_blocked_without_clarity(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _clarify(run: dict) -> dict:
        run["mission_loop"] = {
            "enabled": True,
            "phase": "CLARIFY",
        }
        run["topic"] = "Build something vague"
        return run

    patch_run_meta(session_folder, _clarify)
    out = dispatch(session_folder, RuntimeEvent.MISSION_ADVANCE)
    assert out.skipped is True
    assert out.reason == "guard_blocked"
    assert get_mission_loop(read_run_meta(session_folder))["phase"] == "CLARIFY"


def test_mission_advance_clarify_allowed_when_clarity_met(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _clarify(run: dict) -> dict:
        run["mission_loop"] = {
            "enabled": True,
            "phase": "CLARIFY",
        }
        run["verified_loop"] = {
            "loop_goal": {"text": "fix src/agent_lab/run_meta.py null check"},
        }
        return run

    patch_run_meta(session_folder, _clarify)
    run = read_run_meta(session_folder)
    assert transition_guard_satisfied(run, "clarity_met") is True
    allowed, reason, _, rows = transition_entry_reason(run, RuntimeEvent.MISSION_ADVANCE)
    assert allowed is True
    assert reason == "table_edge"
    assert rows and rows[0].to_phase == "DISCUSS"


def test_discuss_recovery_requires_pending_flag(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _discuss(run: dict) -> dict:
        run["mission_loop"] = {
            "enabled": True,
            "phase": "DISCUSS",
            "discuss_recovery": {"pending": False},
        }
        return run

    patch_run_meta(session_folder, _discuss)
    out = dispatch(session_folder, RuntimeEvent.MISSION_DISCUSS_RECOVERY)
    assert out.skipped is True
    assert out.reason == "guard_blocked"


def test_execute_queue_advance_requires_autorun(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _queue(run: dict) -> dict:
        run["mission_loop"] = {
            "enabled": True,
            "phase": "EXECUTE_QUEUE",
            "pending_action_indices": [1],
            "autonomous_segment": {"active": False},
        }
        return run

    patch_run_meta(session_folder, _queue)
    out = dispatch(session_folder, RuntimeEvent.MISSION_ADVANCE)
    assert out.skipped is True
    assert out.reason == "guard_blocked"
