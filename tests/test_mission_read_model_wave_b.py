from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.human_inbox import create_inbox_item, resolve_inbox_item
from agent_lab.mission.application import MissionApplication
from agent_lab.mission.dual_write import mirror_inbox_resolution
from agent_lab.mission.dual_write_observability import (
    dual_write_counters_snapshot,
    record_dual_write_event,
    reset_dual_write_counters,
)
from agent_lab.mission.kernel import (
    ApproveDiff,
    MarkDiffReady,
    OracleVerdict,
    RecordMerge,
    RecordOracle,
    StartExecution,
)
from agent_lab.run.meta import patch_run_meta
from agent_lab.run.state import RunState
from agent_lab.session import paths as session_paths
from app.server.main import create_app


@pytest.fixture(autouse=True)
def _isolate_run_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # try_begin_run() holds a real cross-process fcntl.flock at config_dir()/run.lock,
    # which collides across xdist workers without a private dir per test. See
    # tests/test_room_resume_stream.py's _isolate_run_lock / commit 2af5e735.
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(tmp_path / ".agent-lab-config"))


@pytest.fixture(autouse=True)
def _isolate_deps_sessions_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # active_sessions_dir() prefers app.server.deps.SESSIONS_DIR over
    # session_paths.SESSIONS_DIR when app.server.deps is already imported (see
    # session/paths.py::active_sessions_dir). A prior test in the same xdist
    # worker that left deps.SESSIONS_DIR pointed elsewhere (via a non-monkeypatch
    # assignment) would otherwise shadow this file's own session_paths patch and
    # 404 every route. Mirror the same tmp_path here so precedence order can't matter.
    import app.server.deps as deps_mod

    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path, raising=False)


def _session(root: Path, name: str) -> Path:
    folder = root / name
    folder.mkdir()
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    (folder / "run.json").write_text(json.dumps({"topic": "ship", "human_inbox": []}), encoding="utf-8")
    return folder


def _read(client: TestClient, session_id: str) -> dict[str, object]:
    response = client.get(f"/api/sessions/{session_id}/mission/read-model")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def test_live_api_read_model_projects_approval_repair_and_oracle_states(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = _session(tmp_path, "lifecycle")
    application = MissionApplication(folder, "ship")
    client = TestClient(create_app(bootstrap=False))

    application.approve_plan()
    approved = _read(client, "lifecycle")
    assert approved["migrated"] is True
    assert approved["state"] == "READY_TO_EXECUTE"
    assert approved["operational_status"] == "READY"
    assert approved["plan"] == {
        "phase": "APPROVED",
        "hash": approved["plan_hash"],
        "approved_hash": approved["approved_plan_hash"],
        "pending_approval": False,
    }

    repository = application.repository
    for command in (StartExecution(), MarkDiffReady(), ApproveDiff(), RecordMerge("merge-before-repair")):
        repository.dispatch(command)
    repository.dispatch(RecordOracle(OracleVerdict.FAIL, "missing marker"))
    repairing = _read(client, "lifecycle")
    assert repairing["state"] == "REPAIRING"
    assert repairing["operational_status"] == "RUNNING"
    assert repairing["repair_attempt"] == 1
    assert repairing["oracle_verdict"] == "fail"
    assert repairing["work_phase"] == "merge_verify"

    for command in (MarkDiffReady(), ApproveDiff(), RecordMerge("merge-after-repair")):
        repository.dispatch(command)
    repository.dispatch(RecordOracle(OracleVerdict.PASS, "repaired"))
    completed = _read(client, "lifecycle")
    assert completed["state"] == "SUCCEEDED"
    assert completed["operational_status"] == "COMPLETED"
    assert completed["oracle_verdict"] == "pass"
    assert completed["next_action"] == "view_result"


def test_live_api_mid_execution_question_answer_resume_and_circuit_shape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    folder = _session(tmp_path, "human-gate")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", folder.name)
    application = MissionApplication(folder, "ship")
    application.approve_plan()
    application.repository.dispatch(StartExecution())
    item = create_inbox_item(
        folder,
        kind="question",
        source="wave_b",
        prompt="Which scope?",
        options=[{"id": "safe", "label": "Safe"}, {"id": "full", "label": "Full"}],
    )
    client = TestClient(create_app(bootstrap=False))

    waiting = _read(client, "human-gate")
    assert waiting["state"] == "EXECUTING"
    assert waiting["operational_status"] == "WAITING_FOR_HUMAN"
    assert waiting["open_execution_gates"] == [{"gate_id": item["id"], "kind": "question"}]
    assert waiting["inbox_items"][0]["prompt"] == "Which scope?"
    assert waiting["inbox_items"][0]["options"] == [
        {"id": "safe", "label": "Safe"},
        {"id": "full", "label": "Full"},
    ]

    resolve_inbox_item(folder, item["id"], selected=["safe"], append_chat=False)
    assert mirror_inbox_resolution(folder, item_id=item["id"], answer="safe")["mirrored"] is True
    resumed = _read(client, "human-gate")
    assert resumed["state"] == "EXECUTING"
    assert resumed["operational_status"] == "RUNNING"
    assert resumed["open_execution_gates"] == []
    assert resumed["inbox_summary"] == {
        "pending_count": 0,
        "pending_questions": 0,
        "pending_builds": 0,
    }

    def mark_paused(run: RunState) -> RunState:
        run["mission_loop"] = {"phase": "MISSION_PAUSED", "circuit_breaker": True}
        return run

    patch_run_meta(folder, mark_paused)
    paused = _read(client, "human-gate")
    assert paused["mission_overview"]["circuit_breaker"] is True


def test_expected_mid_execution_boundary_is_not_a_parity_failure(tmp_path: Path) -> None:
    reset_dual_write_counters()
    folder = _session(tmp_path, "boundary")
    record_dual_write_event(
        folder,
        {
            "enabled": True,
            "operation": "inbox_create",
            "mirrored": False,
            "reason": "mission_not_ready_to_execute",
        },
    )
    counters = dual_write_counters_snapshot()
    assert counters["operations"]["inbox_create"]["expected_boundary"] == 1
    assert counters["operations"]["inbox_create"]["error"] == 0
    reset_dual_write_counters()
