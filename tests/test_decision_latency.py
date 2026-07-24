"""Phase B1 — decision latency open/close + status_line surface."""

from __future__ import annotations

from pathlib import Path

from agent_lab.decision_latency import (
    active_gate,
    record_gate_closed,
    record_gate_opened,
    summarize_decision_latency,
)
from agent_lab.plan.workflow_state import apply_plan_substate_patch
from agent_lab.run.meta import read_run_meta, write_run_meta
from agent_lab.runtime.snapshot import build_runtime_snapshot


def test_record_gate_open_close_and_summarize() -> None:
    run: dict = {}
    assert record_gate_opened(run, kind="plan_approval") is True
    assert record_gate_opened(run, kind="plan_approval") is False
    gate = active_gate(run)
    assert gate is not None
    assert gate["kind"] == "plan_approval"
    event = record_gate_closed(run, kind="plan_approval", action="approve")
    assert event is not None
    assert event["kind"] == "plan_approval"
    assert event["action"] == "approve"
    assert isinstance(event["wait_ms"], int)
    assert active_gate(run) is None
    summary = summarize_decision_latency(run)
    assert summary["count"] == 1
    assert summary["p50_sec"] is not None
    assert summary["p95_sec"] is not None


def test_human_pending_opens_gate(tmp_path: Path) -> None:
    folder = tmp_path / "sess_latency"
    folder.mkdir()
    write_run_meta(folder, {"_session_id": folder.name, "topic": "latency"})
    run = read_run_meta(folder)
    apply_plan_substate_patch(run, phase="HUMAN_PENDING", stamp_orchestration=False)
    assert active_gate(run) is not None
    assert active_gate(run)["kind"] == "plan_approval"
    write_run_meta(folder, run)
    line = build_runtime_snapshot(folder)["status_line"]
    assert line["human_gate_kind"] == "plan_approval"
    assert line["human_gate_opened_at"]


def test_status_line_clears_when_gate_closed(tmp_path: Path) -> None:
    folder = tmp_path / "sess_latency2"
    folder.mkdir()
    write_run_meta(
        folder,
        {
            "_session_id": folder.name,
            "decision_latency": {
                "open": {"kind": "execute_approval", "opened_at": "2026-07-24T00:00:00Z"},
                "events": [],
            },
        },
    )
    line = build_runtime_snapshot(folder)["status_line"]
    assert line["human_gate_kind"] == "execute_approval"
    run = read_run_meta(folder)
    record_gate_closed(run, action="approve")
    write_run_meta(folder, run)
    line2 = build_runtime_snapshot(folder)["status_line"]
    assert line2["human_gate_opened_at"] is None
    assert line2["human_gate_kind"] is None
