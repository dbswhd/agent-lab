from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.mission.loop import enable_mission_loop
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.runtime.snapshot import build_runtime_snapshot
from agent_lab.runtime.work_phase import (
    resolve_work_phase,
    resolve_work_phase_from_mission,
    resolve_work_phase_standalone,
)


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
    folder = tmp_path / "sess-runtime"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    (folder / "plan.md").write_text(_good_plan(), encoding="utf-8")
    return folder


def test_resolve_work_phase_from_mission_paused_uses_resume() -> None:
    assert resolve_work_phase_from_mission("MISSION_PAUSED", resume_phase="VERIFY") == "merge_verify"


def test_resolve_work_phase_standalone_merge_verify() -> None:
    phase = resolve_work_phase_standalone(
        has_plan=True,
        has_pending_execution=False,
        has_dry_run_diff=False,
        pending_agreement=False,
        latest_execution={"status": "merged", "oracle": {"verdict": "fail"}},
    )
    assert phase == "merge_verify"


def test_snapshot_standalone_plan_draft(session_folder: Path) -> None:
    snap = build_runtime_snapshot(session_folder)
    assert snap["mode"] == "standalone"
    assert snap["work_phase"] == "plan_draft"
    assert snap["has_plan"] is True
    assert snap["mission"]["enabled"] is False


def test_snapshot_mission_discuss_phase(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    snap = build_runtime_snapshot(session_folder)
    assert snap["mode"] == "mission"
    assert snap["mission"]["enabled"] is True
    assert snap["work_phase"] == "plan_draft"
    assert snap["mission"]["phase"] in {"DISCUSS", "MISSION_DEFINE"}
    assert "mission_board" in snap
    assert snap["mission_board"]["lane_roles"]["discuss"] == [
        "cursor",
        "codex",
        "claude",
    ]
    assert "turn_budget" in snap
    assert snap["turn_budget"]["budget_pct"] == 0
    assert "merge_checks" in snap
    assert "evidence" in snap


def test_snapshot_pending_execution_execute_pending(session_folder: Path) -> None:
    def _pending(run: dict) -> dict:
        run["executions"] = [
            {
                "id": "exec-1",
                "status": "pending_approval",
                "diff": "--- a\n+++ b\n",
            }
        ]
        return run

    patch_run_meta(session_folder, _pending)
    snap = build_runtime_snapshot(session_folder)
    assert snap["execute"]["has_pending"] is True
    assert snap["execute"]["has_dry_run_diff"] is True
    assert snap["work_phase"] == "merge_verify"


def test_snapshot_matches_legacy_work_phase_resolver(session_folder: Path) -> None:
    def _mission(run_in: dict) -> dict:
        run_in["mission_loop"] = {
            "enabled": True,
            "phase": "MERGE_REVIEW",
        }
        return run_in

    patch_run_meta(session_folder, _mission)
    run = read_run_meta(session_folder)
    ml = run["mission_loop"]
    snap = build_runtime_snapshot(session_folder)
    legacy = resolve_work_phase(
        mission_enabled=True,
        mission_phase=str(ml.get("phase")),
        resume_phase=None,
        has_plan=True,
        has_pending_execution=False,
        has_dry_run_diff=False,
        pending_agreement=False,
        latest_execution=None,
    )
    assert snap["work_phase"] == legacy == "review_needed"


def test_runtime_snapshot_plan_workflow_human_pending(tmp_path: Path) -> None:
    folder = tmp_path / "pw-runtime"
    folder.mkdir()
    (folder / "topic.txt").write_text("plan\n", encoding="utf-8")
    (folder / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (folder / "run.json").write_text(
        '{"plan_workflow":{"enabled":true,"phase":"HUMAN_PENDING"}}',
        encoding="utf-8",
    )
    snap = build_runtime_snapshot(folder)
    assert snap["work_phase"] == "review_needed"


def test_runtime_snapshot_includes_turn_contract_shadow(tmp_path: Path) -> None:
    folder = tmp_path / "tc-runtime"
    folder.mkdir()
    (folder / "run.json").write_text(
        '{"turn_contract":{"contract_id":"guarded_plan","source":"shadow","safety_floor":"guarded_plan","task_kind":"build"}}',
        encoding="utf-8",
    )
    snap = build_runtime_snapshot(folder)
    tc = snap["turn_contract"]
    assert tc is not None
    assert tc["contract_id"] == "guarded_plan"
    assert tc["source"] == "shadow"
    assert tc["mode"] == "shadow"
    assert tc["runtime_applied"] is False


def test_get_runtime_api(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.server.main import app

    monkeypatch.setattr(
        "app.server.routers.runtime.session_folder_or_404",
        lambda _sid: session_folder,
    )
    client = TestClient(app)
    res = client.get("/api/sessions/sess-runtime/runtime")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["session_id"] == "sess-runtime"
    assert body["work_phase"] == "plan_draft"
    assert "next_action" in body
    assert "inbox" in body
    assert "gates" in body
