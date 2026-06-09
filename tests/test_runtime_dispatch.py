from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent_lab.mission_loop import enable_mission_loop, get_mission_loop
from agent_lab.run_meta import patch_run_meta, read_run_meta
from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.runtime import dispatch, dispatch_verify_result


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    folder = tmp_path / "sess-dispatch"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_plan_execute_does_not_import_mission_loop() -> None:
    path = Path(__file__).resolve().parents[1] / "src/agent_lab/plan_execute.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "agent_lab.mission_loop":
            raise AssertionError("plan_execute must not import agent_lab.mission_loop (H2)")


def test_dispatch_dry_run_start_sets_phase(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    out = dispatch(
        session_folder,
        RuntimeEvent.EXECUTE_DRY_RUN_START,
        {"action_index": 1},
    )
    assert out.handled is True
    ml = get_mission_loop(read_run_meta(session_folder))
    assert ml["phase"] == "DRY_RUN"
    assert ml["current_action_index"] == 1


def test_dispatch_dry_run_complete_merge_review(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _dry(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update({"enabled": True, "phase": "DRY_RUN", "current_action_index": 1})
        return run

    patch_run_meta(session_folder, _dry)
    execution = {"id": "exec-1", "action_index": 1, "status": "pending_approval"}
    out = dispatch(
        session_folder,
        RuntimeEvent.EXECUTE_DRY_RUN_COMPLETE,
        {"execution": execution},
    )
    assert out.handled is True
    assert out.phase == "MERGE_REVIEW"


def test_dispatch_verify_pass_mission_done(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _verify(run: dict) -> dict:
        run["mission_loop"] = {
            "enabled": True,
            "phase": "VERIFY",
            "pending_action_indices": [],
            "current_action_index": 1,
            "action_repair_counts": {},
            "max_repair_per_action": 2,
        }
        return run

    patch_run_meta(session_folder, _verify)
    out = dispatch_verify_result(
        session_folder,
        action_index=1,
        verdict="pass",
        reason="ok",
        oracle={"verdict": "pass", "detail": "literal found"},
    )
    assert out.handled is True
    ml = get_mission_loop(read_run_meta(session_folder))
    assert ml["phase"] == "MISSION_DONE"


def test_dispatch_dry_run_start_no_op_when_mission_disabled(session_folder: Path) -> None:
    out = dispatch(
        session_folder,
        RuntimeEvent.EXECUTE_DRY_RUN_START,
        {"action_index": 1},
    )
    assert out.handled is True
    ml = get_mission_loop(read_run_meta(session_folder))
    assert ml.get("enabled") is False
    assert ml.get("phase") != "DRY_RUN"
