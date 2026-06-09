from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent_lab.mission_loop import enable_mission_loop, get_mission_loop, run_plan_gate
from agent_lab.run_meta import read_run_meta
from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.runtime import dispatch


def _good_plan() -> str:
    return """# Plan

## 지금 실행

1. Fix auth
   - 무엇을: JWT validation
   - 어디서: `src/auth.py`
   - 검증: `make test tests/test_auth.py`
"""


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    folder = tmp_path / "sess-discuss"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    (folder / "plan.md").write_text(_good_plan(), encoding="utf-8")
    return folder


def _forbidden_imports(module: str, forbidden_target: str) -> list[str]:
    path = Path(__file__).resolve().parents[1] / "src" / module.replace(".", "/")
    path = path.with_suffix(".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == forbidden_target:
            for alias in node.names:
                hits.append(alias.name)
    return hits


def test_room_does_not_import_mission_or_execute() -> None:
    assert _forbidden_imports("agent_lab.room", "agent_lab.mission_loop") == []
    assert _forbidden_imports("agent_lab.room", "agent_lab.plan_execute") == []


def test_mission_loop_does_not_import_room() -> None:
    assert _forbidden_imports("agent_lab.mission_loop", "agent_lab.room") == []


def test_context_bundle_does_not_import_mission_loop() -> None:
    assert _forbidden_imports("agent_lab.context_bundle", "agent_lab.mission_loop") == []


def test_room_tasks_does_not_import_plan_execute() -> None:
    assert _forbidden_imports("agent_lab.room_tasks", "agent_lab.plan_execute") == []


def test_dispatch_scribe_complete_runs_plan_gate(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    out = dispatch(
        session_folder,
        RuntimeEvent.SCRIBE_COMPLETE,
        {"plan_md": _good_plan()},
    )
    assert out.handled is True
    ml = get_mission_loop(read_run_meta(session_folder))
    assert ml["phase"] in {"PLAN_GATE", "EXECUTE_QUEUE"}
    if ml["phase"] == "EXECUTE_QUEUE":
        assert ml.get("pending_action_indices")


def test_list_plan_actions_via_invoke(session_folder: Path) -> None:
    from agent_lab.runtime.invoke_execute import list_plan_actions

    info = list_plan_actions(session_folder)
    assert info.get("recommended") is not None
