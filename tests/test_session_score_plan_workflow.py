"""Plan workflow KPIs in session_score."""

from __future__ import annotations

from pathlib import Path

from agent_lab.plan.workflow import approve_plan, init_plan_workflow_on_plan_send, set_plan_workflow_phase
from agent_lab.run.meta import patch_run_meta
from agent_lab.session.score import score_session

SAMPLE_PLAN = """# Demo

## 지금 실행

1. Step
   - 무엇을: x
   - 어디서: `a.py`
   - 검증: `pytest`
"""


def test_score_session_plan_workflow_kpis(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_LOOP", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    set_plan_workflow_phase(folder, "HUMAN_PENDING")

    def _proposed(run: dict) -> dict:
        loop = dict(run.get("verified_loop") or {})
        loop["proposed"] = {
            "goal": "Demo",
            "proposed_at": "2026-06-14T10:00:00+00:00",
        }
        run["verified_loop"] = loop
        return run

    patch_run_meta(folder, _proposed)
    approve_plan(folder, plan_md=SAMPLE_PLAN)
    report = score_session(folder)
    scores = report["scores"]
    assert scores["plan_workflow_enabled"] == 1.0
    assert scores["plan_workflow_approved"] == 1.0
    assert scores["plan_workflow_approval_latency_sec"] is not None
    assert report["counts"]["plan_workflow"]["phase"] == "APPROVED"


def test_score_session_no_plan_workflow_kpis_when_disabled(tmp_path: Path) -> None:
    folder = tmp_path / "plain"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    report = score_session(folder)
    assert "plan_workflow_enabled" not in report["scores"]
    assert report["counts"].get("plan_workflow") == {}
