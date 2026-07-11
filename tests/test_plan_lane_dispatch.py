from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.plan.workflow import init_plan_workflow_on_plan_send, set_plan_workflow_phase, tick_plan_workflow_after_turn
from agent_lab.run.meta import read_run_meta
from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.runtime import dispatch


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    folder = tmp_path / "sess-plan-lane"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_plan_workflow_tick_routes_through_runtime(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    init_plan_workflow_on_plan_send(session_folder)
    run = read_run_meta(session_folder)
    run["verified_loop"] = {"loop_goal": {"text": "fix src/agent_lab/room.py"}}
    from agent_lab.run.meta import patch_run_meta

    patch_run_meta(session_folder, lambda r: run | {"verified_loop": run["verified_loop"]})

    tick = tick_plan_workflow_after_turn(
        session_folder,
        synthesize=True,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
    )
    assert tick.get("handled") is not False or tick.get("advance") == "DRAFT"

    orch = read_run_meta(session_folder).get("orchestration") or {}
    assert orch.get("plan_substate") in {"CLARIFY", "DRAFT", "INTAKE"}
    assert "phase" in orch

    trace_path = session_folder / "trace.jsonl"
    assert trace_path.is_file()
    spans = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    dispatch_spans = [s for s in spans if s.get("name") == "runtime_dispatch"]
    assert any(s.get("data", {}).get("event") == "plan.workflow.tick" for s in dispatch_spans)


def test_plan_workflow_tick_rejected_when_approved(session_folder: Path) -> None:
    init_plan_workflow_on_plan_send(session_folder)
    set_plan_workflow_phase(session_folder, "APPROVED")
    out = dispatch(
        session_folder,
        RuntimeEvent.PLAN_WORKFLOW_TICK,
        {
            "synthesize": True,
            "cancelled": False,
            "plan_md": "# plan",
            "plan_before": "",
            "has_pending_inbox_question": False,
        },
    )
    assert out.skipped is True
    assert out.reason == "plan_workflow_approved"
