from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.mission.application import MissionApplication
from agent_lab.session import paths as session_paths
from app.server.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(bootstrap=False))


def _seed_session(tmp_path: Path, session_id: str, *, topic: str = "test topic") -> Path:
    folder = tmp_path / session_id
    folder.mkdir()
    (folder / "run.json").write_text(json.dumps({"topic": topic}), encoding="utf-8")
    (folder / "plan.md").write_text("# Plan\n\nship it\n", encoding="utf-8")
    return folder


def _decode_sse(body: bytes) -> list[dict[str, object]]:
    """Parse simple ``id: ...\ndata: ...\n\n`` SSE frames."""
    events: list[dict[str, object]] = []
    for frame in body.decode("utf-8").split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        event_id: str | None = None
        data: str | None = None
        for line in frame.split("\n"):
            if line.startswith("id: "):
                event_id = line[len("id: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        assert data is not None, f"missing data line in frame: {frame!r}"
        parsed = json.loads(data)
        if event_id is not None:
            parsed["__id_line"] = event_id
        events.append(parsed)
    return events


def test_mission_events_returns_empty_for_legacy_session(
    tmp_path: Path, monkeypatch, client: TestClient
) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "legacy-session"
    folder.mkdir()
    (folder / "run.json").write_text(json.dumps({"topic": "legacy"}), encoding="utf-8")

    response = client.get("/api/sessions/legacy-session/mission/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == ""


def test_mission_events_streams_journal_events(tmp_path: Path, monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = _seed_session(tmp_path, "mission-session")
    MissionApplication(folder, "test topic").approve_plan()

    response = client.get("/api/sessions/mission-session/mission/events")

    assert response.status_code == 200
    events = _decode_sse(response.content)
    cursors = [event["event_cursor"] for event in events]
    assert cursors == [1, 2]
    assert {event["event_type"] for event in events} == {"PlanOpened", "PlanApproved"}
    assert all(isinstance(event["payload"], dict) for event in events)


def test_mission_events_respects_last_event_id_header(tmp_path: Path, monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = _seed_session(tmp_path, "mission-session")
    MissionApplication(folder, "test topic").approve_plan()

    response = client.get(
        "/api/sessions/mission-session/mission/events",
        headers={"Last-Event-ID": "1"},
    )

    assert response.status_code == 200
    events = _decode_sse(response.content)
    assert len(events) == 1
    assert events[0]["event_cursor"] == 2
    assert events[0]["event_type"] == "PlanApproved"


def test_mission_events_rejects_negative_last_event_id(tmp_path: Path, monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "bad-session"
    folder.mkdir()
    (folder / "run.json").write_text(json.dumps({"topic": "bad"}), encoding="utf-8")

    response = client.get(
        "/api/sessions/bad-session/mission/events",
        headers={"Last-Event-ID": "-1"},
    )

    assert response.status_code == 400


def test_mission_events_rejects_invalid_last_event_id(tmp_path: Path, monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "bad-session"
    folder.mkdir()
    (folder / "run.json").write_text(json.dumps({"topic": "bad"}), encoding="utf-8")

    response = client.get(
        "/api/sessions/bad-session/mission/events",
        headers={"Last-Event-ID": "not-a-number"},
    )

    assert response.status_code == 400


def test_mission_events_includes_id_line_matching_cursor(
    tmp_path: Path, monkeypatch, client: TestClient
) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = _seed_session(tmp_path, "mission-session")
    MissionApplication(folder, "test topic").approve_plan()

    response = client.get("/api/sessions/mission-session/mission/events")

    events = _decode_sse(response.content)
    for event in events:
        assert event["__id_line"] == str(event["event_cursor"])


def test_mission_events_returns_404_for_missing_session(client: TestClient) -> None:
    response = client.get("/api/sessions/does-not-exist/mission/events")

    assert response.status_code == 404


def test_mission_events_replays_after_last_event_id_zero(
    tmp_path: Path, monkeypatch, client: TestClient
) -> None:
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = _seed_session(tmp_path, "mission-session")
    MissionApplication(folder, "test topic").approve_plan()

    response = client.get(
        "/api/sessions/mission-session/mission/events",
        headers={"Last-Event-ID": "0"},
    )

    events = _decode_sse(response.content)
    assert [event["event_cursor"] for event in events] == [1, 2]
