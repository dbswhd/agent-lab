from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.human_inbox import (
    compute_inbox_pending,
    append_inbox_item,
    create_inbox_item,
    inbox_items_for_folder,
    new_inbox_item,
    supersede_pending_inbox,
)
from agent_lab.mission.application import MissionApplication, MissionApplicationError
from agent_lab.mission.journal import MissionJournal
from agent_lab.mission.loop import trigger_circuit_breaker
from agent_lab.plan.workflow_clarify import build_clarify_context_block
from agent_lab.run.meta import read_run_meta
from app.server.main import create_app


def _session(tmp_path: Path, name: str = "authority") -> Path:
    folder = tmp_path / name
    folder.mkdir()
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    (folder / "run.json").write_text(json.dumps({"topic": "ship"}), encoding="utf-8")
    return folder


@pytest.fixture(autouse=True)
def _authority_cohort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY_SESSIONS", "authority")


def test_authority_open_writes_item_to_mission_journal_without_run_writer(tmp_path: Path) -> None:
    folder = _session(tmp_path)

    item = create_inbox_item(folder, kind="question", source="test", prompt="Which scope?", options=[{"id": "safe"}])

    run = read_run_meta(folder)
    assert "human_inbox" not in run
    mission = MissionApplication(folder, "ship").load()
    assert mission.inbox_items == (item,)
    assert [event.event_type for event in MissionJournal(folder / ".agent-lab" / "mission-events.jsonl").load()] == [
        "InboxItemOpened",
        "ExecutionGateOpened",
    ]


def test_authority_resolve_is_atomic_and_projects_read_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _session(tmp_path)
    item = create_inbox_item(folder, kind="question", source="test", prompt="Which scope?")

    application = MissionApplication(folder, "ship")
    resolved = application.resolve_inbox_item(item["id"], selected=["safe"], expected_version=0)

    assert resolved.inbox_items[0]["status"] == "resolved"
    assert resolved.inbox_items[0]["resolved_choice"] == "safe"
    assert resolved.open_gates == ()
    assert "human_inbox" not in read_run_meta(folder)
    records = MissionJournal(folder / ".agent-lab" / "mission-events.jsonl").load()
    assert {records[-1].event_type, records[-2].event_type} == {
        "InboxItemResolved",
        "ExecutionGateClosed",
    }

    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", tmp_path)
    payload = TestClient(create_app(bootstrap=False)).get(f"/api/sessions/{folder.name}/mission/read-model").json()
    assert payload["migrated"] is True
    assert payload["inbox_items"][0]["status"] == "resolved"


def test_authority_resolve_rejects_stale_item_version_without_mutation(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    item = create_inbox_item(folder, kind="question", source="test", prompt="Which scope?")
    application = MissionApplication(folder, "ship")
    application.resolve_inbox_item(item["id"], selected=["safe"], expected_version=0)

    with pytest.raises(MissionApplicationError):
        application.resolve_inbox_item(item["id"], selected=["full"], expected_version=0)

    restored = application.load()
    assert restored.inbox_items[0]["resolved_choice"] == "safe"
    assert len(MissionJournal(folder / ".agent-lab" / "mission-events.jsonl").load()) == 4


def test_authority_internal_reads_use_journal_items(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    item = create_inbox_item(folder, kind="question", source="test", prompt="Which scope?")

    assert inbox_items_for_folder(folder)[0]["id"] == item["id"]
    assert compute_inbox_pending({"_session_folder": str(folder)}) is True

    MissionApplication(folder, "ship").resolve_inbox_item(item["id"], decision="safe", expected_version=0)

    context = build_clarify_context_block(folder)
    assert "Which scope?" in context
    assert "safe" in context


def test_authority_supersede_closes_journal_gate_without_run_writer(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    item = create_inbox_item(folder, kind="question", source="test", prompt="Which scope?")

    assert supersede_pending_inbox(folder, human_turn_id=3) == 1

    mission = MissionApplication(folder, "ship").load()
    assert mission.inbox_items[0]["status"] == "superseded"
    assert mission.open_gates == ()
    assert "human_inbox" not in read_run_meta(folder)
    assert item["id"] == mission.inbox_items[0]["id"]


def test_authority_direct_append_writer_routes_to_journal(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    run: dict[str, object] = {"topic": "ship", "_session_folder": str(folder)}
    item = new_inbox_item(kind="question", source="harvest", prompt="Which scope?")

    append_inbox_item(run, item)

    assert "human_inbox" not in run
    assert MissionApplication(folder, "ship").load().inbox_items == (item,)


def test_authority_circuit_breaker_writer_routes_to_journal(tmp_path: Path) -> None:
    folder = _session(tmp_path)

    trigger_circuit_breaker(folder, reason="test")

    assert "human_inbox" not in read_run_meta(folder)
    mission = MissionApplication(folder, "ship").load()
    assert mission.inbox_items[0]["source"] == "mission_circuit_break"
    assert mission.open_gates[0].gate_id == mission.inbox_items[0]["id"]


def test_authority_http_resolve_uses_journal_without_legacy_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _session(tmp_path)
    item = create_inbox_item(folder, kind="question", source="test", prompt="Which scope?")
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", tmp_path)
    client = TestClient(create_app(bootstrap=False))

    inbox_response = client.get(f"/api/sessions/{folder.name}/inbox")
    assert inbox_response.status_code == 200
    assert inbox_response.json()["human_inbox"][0]["id"] == item["id"]

    response = client.post(
        f"/api/sessions/{folder.name}/inbox/{item['id']}/resolve",
        json={"selected": ["safe"], "expected_version": 0, "append_chat": False},
    )
    assert response.status_code == 200
    assert response.json()["mission_dual_write"]["authority"] == "mission_journal"
    assert "human_inbox" not in read_run_meta(folder)
