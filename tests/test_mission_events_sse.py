from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.mission.application import MissionApplication
from agent_lab.session import paths as session_paths
from app.server.main import create_app
from app.server.routers.mission_events import mission_events_stream


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
        if not frame or frame.startswith(":"):
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


def _drain(agen):
    """Run an async generator to completion, mirroring test_room_resume_stream.py."""

    async def _run():
        out = []
        async for item in agen:
            out.append(item)
        return out

    return asyncio.run(_run())


def _disconnect_after(n: int):
    """Fake ``is_disconnected`` that stays connected for ``n`` poll iterations."""
    calls = {"count": 0}

    async def _is_disconnected() -> bool:
        calls["count"] += 1
        return calls["count"] > n

    return _is_disconnected


async def _never_disconnected() -> bool:
    return False


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


def test_mission_events_returns_404_for_missing_session(client: TestClient) -> None:
    response = client.get("/api/sessions/does-not-exist/mission/events")

    assert response.status_code == 404


# --- mission_events_stream (direct generator tests, mirroring _room_resume_events) ---
#
# A live TestClient request never disconnects mid-stream, so a mission that
# hasn't reached a terminal state would tail forever if driven through the
# HTTP layer. These tests drive the extracted generator directly with a fake
# ``is_disconnected``, matching how test_room_resume_stream.py covers
# ``_room_resume_events``.


def test_mission_events_stream_replays_backlog_then_disconnects(tmp_path: Path) -> None:
    folder = _seed_session(tmp_path, "mission-session")
    MissionApplication(folder, "test topic").approve_plan()

    events = _drain(
        mission_events_stream(folder, after_cursor=0, is_disconnected=_disconnect_after(1), poll_sec=0.01)
    )

    cursors = [event["event_cursor"] for event in events if event is not None]
    assert cursors == [1, 2]
    assert {event["event_type"] for event in events} == {"PlanOpened", "PlanApproved"}
    assert all(isinstance(event["payload"], dict) for event in events)


def test_mission_events_stream_respects_after_cursor(tmp_path: Path) -> None:
    folder = _seed_session(tmp_path, "mission-session")
    MissionApplication(folder, "test topic").approve_plan()

    events = _drain(
        mission_events_stream(folder, after_cursor=1, is_disconnected=_disconnect_after(1), poll_sec=0.01)
    )

    assert len(events) == 1
    assert events[0]["event_cursor"] == 2
    assert events[0]["event_type"] == "PlanApproved"


def test_mission_events_stream_returns_immediately_when_client_already_gone(tmp_path: Path) -> None:
    folder = _seed_session(tmp_path, "mission-session")
    MissionApplication(folder, "test topic").approve_plan()

    async def already_disconnected() -> bool:
        return True

    events = _drain(
        mission_events_stream(folder, after_cursor=0, is_disconnected=already_disconnected, poll_sec=0.01)
    )
    assert events == []


def test_mission_events_stream_closes_when_mission_reaches_terminal_state(tmp_path: Path) -> None:
    """A mission that never leaves a non-terminal state would tail forever;
    one that reaches SUCCEEDED/FAILED/CANCELLED must close on its own so a
    real (non-faked) HTTP client isn't left hanging."""
    folder = _seed_session(tmp_path, "mission-session")
    app = MissionApplication(folder, "test topic")
    app.approve_plan()
    from agent_lab.mission.kernel import (
        ApproveDiff,
        MarkDiffReady,
        OracleVerdict,
        RecordMerge,
        RecordOracle,
        StartExecution,
    )

    repo = app.repository
    mission = repo.dispatch(StartExecution())
    mission = repo.dispatch(MarkDiffReady())
    mission = repo.dispatch(ApproveDiff())
    mission = repo.dispatch(RecordMerge("abc123"))
    mission = repo.dispatch(RecordOracle(OracleVerdict.PASS, "looks good"))
    assert mission.state.value == "SUCCEEDED"

    events = _drain(
        mission_events_stream(folder, after_cursor=0, is_disconnected=_never_disconnected, poll_sec=0.01)
    )
    # Replays the full backlog, then closes on its own (no disconnect faked)
    # because the mission is terminal — never enters the poll-forever branch.
    assert [event["event_cursor"] for event in events if event is not None] == [1, 2, 3, 4, 5, 6, 7]


def test_mission_events_stream_tails_new_events_while_open(tmp_path: Path) -> None:
    folder = _seed_session(tmp_path, "mission-session")
    app = MissionApplication(folder, "test topic")
    app.approve_plan()

    calls = {"n": 0}

    async def disconnect_after_new_event_seen() -> bool:
        calls["n"] += 1
        if calls["n"] == 2:
            from agent_lab.mission.kernel import StartExecution

            app.repository.dispatch(StartExecution())
        return calls["n"] > 3

    events = _drain(
        mission_events_stream(
            folder, after_cursor=0, is_disconnected=disconnect_after_new_event_seen, poll_sec=0.01
        )
    )
    cursors = [event["event_cursor"] for event in events if event is not None]
    # Initial backlog (1, 2) plus the event appended mid-poll (3).
    assert cursors == [1, 2, 3]


def test_mission_events_stream_yields_keepalive_when_idle(tmp_path: Path) -> None:
    folder = _seed_session(tmp_path, "mission-session")
    MissionApplication(folder, "test topic").approve_plan()

    events = _drain(
        mission_events_stream(
            folder,
            after_cursor=0,
            is_disconnected=_disconnect_after(2),
            poll_sec=0.01,
            keepalive_sec=0.0,
        )
    )
    assert None in events


def test_mission_events_endpoint_streams_journal_events_over_http(
    tmp_path: Path, monkeypatch, client: TestClient
) -> None:
    """HTTP-level smoke test: a mission that reaches a terminal state closes
    the connection on its own, so a real TestClient request completes without
    needing a faked disconnect."""
    monkeypatch.setattr(session_paths, "SESSIONS_DIR", tmp_path)
    folder = _seed_session(tmp_path, "mission-session")
    app = MissionApplication(folder, "test topic")
    app.approve_plan()
    from agent_lab.mission.kernel import (
        ApproveDiff,
        MarkDiffReady,
        OracleVerdict,
        RecordMerge,
        RecordOracle,
        StartExecution,
    )

    repo = app.repository
    repo.dispatch(StartExecution())
    repo.dispatch(MarkDiffReady())
    repo.dispatch(ApproveDiff())
    repo.dispatch(RecordMerge("abc123"))
    repo.dispatch(RecordOracle(OracleVerdict.PASS, "looks good"))

    response = client.get("/api/sessions/mission-session/mission/events")

    assert response.status_code == 200
    events = _decode_sse(response.content)
    assert [event["event_cursor"] for event in events] == [1, 2, 3, 4, 5, 6, 7]
    for event in events:
        assert event["__id_line"] == str(event["event_cursor"])
