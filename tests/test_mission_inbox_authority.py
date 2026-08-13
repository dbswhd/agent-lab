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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known gap in the half-finished journal migration. The harvest path in "
        "room/session_persist.py appends inside patch_run_meta(), whose run dict "
        "carries no '_session_folder', so append_inbox_item() takes the legacy "
        "run.json branch instead of the journal one exercised by "
        "::test_authority_direct_append_writer_routes_to_journal. Its compensating "
        "call, mission.dual_write.sync_open_gates_for_inbox_items(), early-returns "
        "on dual_write_enabled(), which no run profile turns on -- see "
        "tests/test_m6_checkpoint_bridges_flags.py. Net effect: harvested items get "
        "no Mission gate. They still reach the read model, which merges run.json, so "
        "this is a journal/run.json split rather than a disappearing decision. "
        "Remove this marker when the harvest path routes through MissionApplication."
    ),
)
def test_authority_harvested_item_opens_a_journal_gate(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    MissionApplication(folder, "ship").approve_plan()
    item = new_inbox_item(kind="question", source="orchestrator", prompt="harvested?")

    from agent_lab.run.meta import patch_run_meta

    patch_run_meta(folder, lambda run: append_inbox_item(run, item))

    mission = MissionApplication(folder, "ship").load()
    assert [gate.gate_id for gate in mission.open_gates] == [item["id"]]


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


def test_mission_authority_full_traffic_sentinel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agent_lab.mission.inbox_application import mission_authority_enabled

    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY_SESSIONS", "*")
    assert mission_authority_enabled(tmp_path / "any-session") is True
    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY_SESSIONS", "__all__")
    assert mission_authority_enabled(tmp_path / "other") is True


def test_mission_authority_empty_allowlist_still_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agent_lab.mission.inbox_application import mission_authority_enabled

    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY_SESSIONS", "")
    assert mission_authority_enabled(tmp_path / "authority") is False
