from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent_lab.mission.application import MissionApplication
from agent_lab.session import paths as session_paths
from app.server.main import create_app

_LEGACY_COMPOSITE_KEYS = {
    "plan": {
        "phase": None,
        "hash": None,
        "approved_hash": None,
        "pending_approval": False,
    },
    "work_phase": "plan_draft",
    "mission_overview": {
        "phase_label": "LEGACY",
        "paused": False,
        "circuit_breaker": False,
        "pending_inbox_count": 0,
    },
    "inbox_summary": {
        "pending_count": 0,
        "pending_questions": 0,
        "pending_builds": 0,
    },
    "inbox_items": [],
}


def test_read_model_route_marks_legacy_session_without_journal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "legacy-session"
    folder.mkdir()
    (folder / "run.json").write_text(json.dumps({"topic": "legacy topic"}), encoding="utf-8")

    response = TestClient(create_app(bootstrap=False)).get("/api/sessions/legacy-session/mission/read-model")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "legacy-session",
        "migrated": False,
        "source": "legacy",
        "mission_id": None,
        "goal": "legacy topic",
        "state": None,
        "version": None,
        "plan_revision": None,
        "plan_hash": None,
        "approved_plan_hash": None,
        "repair_attempt": None,
        "max_repair_attempts": None,
        "oracle_verdict": None,
        "next_action": "legacy_route",
        "event_cursor": 0,
        "operational_status": None,
        "open_execution_gates": [],
        "legacy_phase": None,
        **_LEGACY_COMPOSITE_KEYS,
    }


def test_read_model_route_legacy_composites_from_run_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "legacy-enriched"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "topic": "legacy topic",
                "plan_workflow": {"phase": "HUMAN_PENDING", "plan_hash_at_approval": "abc"},
                "mission_loop": {"phase": "DISCUSS", "circuit_breaker": False},
                "human_inbox": [
                    {
                        "id": "q1",
                        "kind": "question",
                        "status": "pending",
                        "prompt": "pick one",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    response = TestClient(create_app(bootstrap=False)).get("/api/sessions/legacy-enriched/mission/read-model")

    assert response.status_code == 200
    payload = response.json()
    assert payload["migrated"] is False
    assert payload["legacy_phase"] == "DISCUSS"
    assert payload["plan"] == {
        "phase": "HUMAN_PENDING",
        "hash": "abc",
        "approved_hash": None,
        "pending_approval": True,
    }
    assert payload["work_phase"] == "plan_draft"
    assert payload["mission_overview"]["phase_label"] == "DISCUSS"
    assert payload["inbox_summary"] == {
        "pending_count": 1,
        "pending_questions": 1,
        "pending_builds": 0,
    }
    assert payload["inbox_items"] == []


def test_read_model_route_projects_mission_journal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "mission-session"
    folder.mkdir()
    (folder / "run.json").write_text(json.dumps({"topic": "new mission"}), encoding="utf-8")
    (folder / "plan.md").write_text("# Plan\n\nship it\n", encoding="utf-8")
    MissionApplication(folder, "new mission").approve_plan()

    response = TestClient(create_app(bootstrap=False)).get("/api/sessions/mission-session/mission/read-model")

    assert response.status_code == 200
    payload = response.json()
    assert payload["migrated"] is True
    assert payload["source"] == "mission_journal"
    assert payload["state"] == "READY_TO_EXECUTE"
    assert payload["next_action"] == "start_execution"
    assert payload["version"] == 2
    assert payload["event_cursor"] == 2
    assert payload["operational_status"] == "READY"
    assert payload["open_execution_gates"] == []
    assert payload["plan"]["phase"] == "APPROVED"
    assert payload["plan"]["pending_approval"] is False
    assert payload["work_phase"] == "execute_pending"
    assert payload["mission_overview"] == {
        "phase_label": "READY",
        "paused": False,
        "circuit_breaker": False,
        "pending_inbox_count": 0,
    }
    assert payload["inbox_summary"] == {
        "pending_count": 0,
        "pending_questions": 0,
        "pending_builds": 0,
    }
    assert payload["inbox_items"] == []


def test_read_model_route_projects_joined_inbox_rows(tmp_path: Path, monkeypatch) -> None:
    from agent_lab.mission.kernel import OpenExecutionGate

    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "mission-inbox"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "topic": "joined mission",
                "human_inbox": [
                    {
                        "id": "gate-2",
                        "kind": "question",
                        "status": "pending",
                        "prompt": "Second",
                        "options": [{"label": "B"}],
                    },
                    {
                        "id": "gate-1",
                        "kind": "question",
                        "status": "pending",
                        "prompt": "First",
                        "options": [{"label": "A"}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (folder / "plan.md").write_text("# Plan\n\nship it\n", encoding="utf-8")
    app = MissionApplication(folder, "joined mission")
    app.approve_plan()
    app.repository.dispatch(OpenExecutionGate("gate-1", "question"))
    app.repository.dispatch(OpenExecutionGate("gate-2", "question"))

    response = TestClient(create_app(bootstrap=False)).get("/api/sessions/mission-inbox/mission/read-model")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["inbox_items"]] == ["gate-1", "gate-2"]
    assert payload["inbox_items"][0]["prompt"] == "First"
    # §7.3 — every item carries its optimistic-lock version (0 until answered).
    assert [item["decision_version"] for item in payload["inbox_items"]] == [0, 0]
    assert payload["inbox_summary"] == {
        "pending_count": 2,
        "pending_questions": 2,
        "pending_builds": 0,
    }


def test_read_model_route_reflects_decision_version_after_guard_answer(tmp_path: Path, monkeypatch) -> None:
    """§7.3 — decision_version advances once guard_inbox_answer records an
    answer, so a client polling the read-model sees the version it must send
    back on the next (or a stale retried) resolve call."""
    from agent_lab.mission.kernel import OpenExecutionGate

    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "mission-decision-version"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "topic": "decision version",
                "human_inbox": [
                    {
                        "id": "gate-1",
                        "kind": "question",
                        "status": "pending",
                        "prompt": "Scope?",
                        "options": [{"label": "A"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (folder / "plan.md").write_text("# Plan\n\nship it\n", encoding="utf-8")
    app = MissionApplication(folder, "decision version")
    app.approve_plan()
    app.repository.dispatch(OpenExecutionGate("gate-1", "question"))

    client = TestClient(create_app(bootstrap=False))
    before = client.get("/api/sessions/mission-decision-version/mission/read-model").json()
    assert before["inbox_items"][0]["decision_version"] == 0

    app.guard_inbox_answer("gate-1", "narrow", expected_version=0)

    after = client.get("/api/sessions/mission-decision-version/mission/read-model").json()
    assert after["inbox_items"][0]["decision_version"] == 1
