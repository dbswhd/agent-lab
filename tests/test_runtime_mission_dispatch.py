from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.mission_loop import enable_mission_loop, get_mission_loop, run_plan_gate
from agent_lab.run_meta import patch_run_meta, read_run_meta
from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.runtime import dispatch


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    folder = tmp_path / "sess-mission-dispatch"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def _good_plan() -> str:
    return """# Plan

## 지금 실행

1. Fix auth module
   - 무엇을: JWT validation in `src/auth.py`
   - 어디서: `src/auth.py`
   - 검증: `make test tests/test_auth.py`
"""


def _bad_plan() -> str:
    return "# Plan\n\n(no numbered actions)\n"


def test_dispatch_mission_enable(session_folder: Path) -> None:
    out = dispatch(
        session_folder,
        RuntimeEvent.MISSION_ENABLE,
        {"start_autonomous": False},
    )
    assert out.handled is True
    ml = get_mission_loop(read_run_meta(session_folder))
    assert ml.get("enabled") is True


def test_dispatch_mission_plan_gate_ok(session_folder: Path) -> None:
    enable_mission_loop(session_folder, start_autonomous=False)
    (session_folder / "plan.md").write_text(_good_plan(), encoding="utf-8")
    out = dispatch(
        session_folder,
        RuntimeEvent.MISSION_PLAN_GATE,
        {"plan_md": _good_plan()},
    )
    assert out.handled is True
    assert out.phase == "EXECUTE_QUEUE"
    result = out.result if isinstance(out.result, dict) else {}
    assert result.get("status") == "ok"


def test_dispatch_mission_advance_skipped_without_autorun(session_folder: Path) -> None:
    enable_mission_loop(session_folder, start_autonomous=False)
    run_plan_gate(session_folder, _good_plan())

    out = dispatch(session_folder, RuntimeEvent.MISSION_ADVANCE)
    assert out.handled is True
    assert out.skipped is True


def test_dispatch_mission_pause(session_folder: Path) -> None:
    enable_mission_loop(session_folder, start_autonomous=True)

    def _queue(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update({"enabled": True, "phase": "EXECUTE_QUEUE", "current_action_index": 1})
        return run

    patch_run_meta(session_folder, _queue)
    out = dispatch(
        session_folder,
        RuntimeEvent.MISSION_PAUSE,
        {"reason": "test_stop", "cleanup_executions": False},
    )
    assert out.handled is True
    ml = get_mission_loop(read_run_meta(session_folder))
    assert ml.get("phase") == "MISSION_PAUSED"


def test_dispatch_mission_circuit_breaker(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    out = dispatch(
        session_folder,
        RuntimeEvent.MISSION_CIRCUIT_BREAKER,
        {"reason": "test_trip", "inbox_prompt": "manual trip"},
    )
    assert out.handled is True
    ml = get_mission_loop(read_run_meta(session_folder))
    assert ml.get("circuit_breaker") is True
    assert ml.get("phase") == "MISSION_PAUSED"


def test_dispatch_mission_resume(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _paused(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "MISSION_PAUSED",
                "last_partial": {"resume_phase": "EXECUTE_QUEUE"},
            }
        )
        return run

    patch_run_meta(session_folder, _paused)
    out = dispatch(
        session_folder,
        RuntimeEvent.MISSION_RESUME,
        {"resume_phase": "EXECUTE_QUEUE"},
    )
    assert out.handled is True
    ml = get_mission_loop(read_run_meta(session_folder))
    assert ml.get("phase") == "EXECUTE_QUEUE"


def test_dispatch_run_cancel(session_folder: Path) -> None:
    enable_mission_loop(session_folder, start_autonomous=True)

    def _dry(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update({"enabled": True, "phase": "DRY_RUN", "current_action_index": 1})
        return run

    patch_run_meta(session_folder, _dry)
    out = dispatch(session_folder, RuntimeEvent.RUN_CANCEL, {"reason": "global_cancel"})
    assert out.handled is True
    ml = get_mission_loop(read_run_meta(session_folder))
    assert ml.get("phase") == "MISSION_PAUSED"


def test_dispatch_mission_plan_gate_reject_via_runtime(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    out = dispatch(
        session_folder,
        RuntimeEvent.MISSION_PLAN_GATE,
        {"plan_md": _bad_plan()},
    )
    assert out.handled is True
    ml = get_mission_loop(read_run_meta(session_folder))
    assert ml.get("phase") == "DISCUSS"


def test_all_mission_events_have_handlers(session_folder: Path) -> None:
    """Every mission.* event routes to a handler (handled=True or explicit skip)."""
    enable_mission_loop(session_folder, start_autonomous=False)
    events = [
        RuntimeEvent.MISSION_ENABLE,
        RuntimeEvent.MISSION_PLAN_GATE,
        RuntimeEvent.MISSION_ADVANCE,
        RuntimeEvent.MISSION_PAUSE,
        RuntimeEvent.MISSION_RESUME,
        RuntimeEvent.MISSION_CIRCUIT_BREAKER,
        RuntimeEvent.MISSION_CIRCUIT_CLEAR,
        RuntimeEvent.MISSION_DISCUSS_RECOVERY,
    ]
    for event in events:
        payload: dict = {}
        if event == RuntimeEvent.MISSION_PLAN_GATE:
            payload = {"plan_md": _good_plan()}
        if event == RuntimeEvent.MISSION_CIRCUIT_BREAKER:
            payload = {"reason": "handler_probe"}
        out = dispatch(session_folder, event, payload or None)
        assert out.handled is True, f"{event.value} was not handled: {out.reason}"
