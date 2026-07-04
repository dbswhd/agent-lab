"""N4 Autonomy Ladder — level inference and run.json payload."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.autonomy_ladder import (
    infer_effective_autonomy_level,
    observe_autonomy_level_change,
    public_autonomy_payload,
    record_autonomy_transition,
    resolve_display_autonomy_level,
    stored_autonomy_level,
)
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.trust_budget import set_trust_budget


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "sess-autonomy"
    folder.mkdir()
    patch_run_meta(folder, lambda run: {**run, "status": "active"})
    return folder


def test_default_level_is_l0(session_folder: Path) -> None:
    run = read_run_meta(session_folder)
    assert infer_effective_autonomy_level(run) == "L0"
    assert stored_autonomy_level(run) == "L0"
    payload = public_autonomy_payload(run)
    assert payload["display_level"] == "L0"
    assert payload["level_name"] == "Manual"


def test_trust_budget_implies_l2(session_folder: Path) -> None:
    set_trust_budget(session_folder, {"auto_merge_remaining": 2, "auto_merge_total": 5})
    run = read_run_meta(session_folder)
    assert infer_effective_autonomy_level(run) == "L2"
    payload = public_autonomy_payload(run)
    assert payload["trust_budget"]["auto_merge_remaining"] == 2


def test_mission_autonomous_segment_implies_l3(session_folder: Path) -> None:
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "mission_loop": {
                "enabled": True,
                "phase": "EXECUTE_QUEUE",
                "autonomous_segment": {"active": True},
            },
        },
    )
    run = read_run_meta(session_folder)
    assert infer_effective_autonomy_level(run) == "L3"


def test_stored_level_caps_display(session_folder: Path) -> None:
    set_trust_budget(session_folder, {"auto_merge_remaining": 1, "auto_merge_total": 3})
    patch_run_meta(
        session_folder,
        lambda run: {**run, "autonomy": {"level": "L1"}},
    )
    run = read_run_meta(session_folder)
    assert infer_effective_autonomy_level(run) == "L2"
    assert resolve_display_autonomy_level(run) == "L1"


def test_record_autonomy_transition(session_folder: Path) -> None:
    payload = record_autonomy_transition(
        session_folder,
        to_level="L1",
        reason="human_promote",
        trigger="human",
        from_level="L0",
    )
    assert payload["level"] == "L1"
    transitions = payload["transitions"]
    assert len(transitions) == 1
    assert transitions[0]["from"] == "L0"
    assert transitions[0]["to"] == "L1"


def test_auto_approve_env_implies_l1(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "low")
    run = read_run_meta(session_folder)
    assert infer_effective_autonomy_level(run) == "L1"
    payload = public_autonomy_payload(run)
    assert payload["signals"]["auto_approve_enabled"] is True


def test_runtime_snapshot_includes_autonomy(session_folder: Path) -> None:
    from agent_lab.runtime.snapshot import build_runtime_snapshot

    set_trust_budget(session_folder, {"auto_merge_remaining": 1, "auto_merge_total": 2})
    snap = build_runtime_snapshot(session_folder)
    assert snap["autonomy"]["display_level"] == "L2"


def test_observe_autonomy_level_change_on_trust_budget(session_folder: Path) -> None:
    payload = set_trust_budget(
        session_folder, {"auto_merge_remaining": 2, "auto_merge_total": 5}
    )
    assert payload["auto_merge_total"] == 5
    run = read_run_meta(session_folder)
    autonomy = public_autonomy_payload(run)
    transitions = autonomy["transitions"]
    assert len(transitions) >= 1
    assert transitions[-1]["from"] == "L0"
    assert transitions[-1]["to"] == "L2"
    assert transitions[-1]["trigger"] == "auto"
    assert autonomy["display_level"] == "L2"


def test_consume_trust_budget_records_demotion(session_folder: Path) -> None:
    from agent_lab.trust_budget import consume_auto_merge_budget

    set_trust_budget(
        session_folder, {"auto_merge_remaining": 1, "auto_merge_total": 1}
    )
    consume_auto_merge_budget(session_folder)
    run = read_run_meta(session_folder)
    autonomy = public_autonomy_payload(run)
    assert autonomy["effective_level"] == "L0"
    demotions = [t for t in autonomy["transitions"] if t.get("trigger") == "demotion"]
    assert demotions
    assert demotions[-1]["to"] == "L0"


@pytest.fixture
def autonomy_api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    sessions_dir = tmp_path / "sessions"
    folder = sessions_dir / "sess-autonomy"
    folder.mkdir(parents=True)
    patch_run_meta(folder, lambda run: {**run, "status": "active"})
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    from app.server.main import app

    return TestClient(app), folder


def test_autonomy_api_endpoint(autonomy_api_client) -> None:
    client, folder = autonomy_api_client
    set_trust_budget(folder, {"auto_merge_remaining": 1, "auto_merge_total": 2})
    res = client.get(f"/api/sessions/{folder.name}/autonomy")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["autonomy"]["display_level"] == "L2"
    assert body["autonomy"]["transitions"]
