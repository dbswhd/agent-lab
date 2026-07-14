from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_run_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # /api/room/runs's streaming success path drives _run_with_lock() ->
    # try_begin_run(), a real cross-process fcntl lock at config_dir()/
    # run.lock. Without a private dir per test, concurrent xdist workers
    # race on the shared machine-wide lock file (see
    # tests/test_run_control.py's _isolate_run_lock for the full story).
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(tmp_path / ".agent-lab-config"))


def test_room_run_rejects_loop_without_plan_before_session_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "0")

    from app.server.main import app

    client = TestClient(app)
    res = client.post(
        "/api/room/runs",
        data={
            "topic": "loop should require plan",
            "agents": '["cursor"]',
            "mode": "discuss",
            "synthesize": "false",
            "turn_profile": "loop",
        },
    )

    assert res.status_code == 422
    assert res.json()["detail"] == "loop requires plan"
    assert not list(tmp_path.iterdir())


def test_room_run_rejects_loop_when_selected_model_is_not_loop_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    from dataclasses import replace

    from fastapi.testclient import TestClient

    import agent_lab.model_policy as model_policy
    import agent_lab.session as session_mod
    import app.server.deps as deps_mod
    import app.server.routers.room as room_router

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(room_router, "_agents_not_ready", lambda _agents: [])

    real = model_policy.agent_model_profiles()["cursor"]
    incapable = replace(
        real,
        model_id="incapable-local",
        supports_tools=False,
        supports_inbox_mcp=False,
        supports_json_envelope=False,
    )
    monkeypatch.setattr(
        model_policy,
        "model_profile_for",
        lambda agent_id, model_id=None: incapable if agent_id == "cursor" else real,
    )

    from app.server.main import app

    client = TestClient(app)
    res = client.post(
        "/api/room/runs",
        data={
            "topic": "loop should enforce model readiness",
            "agents": '["cursor"]',
            "mode": "plan",
            "synthesize": "true",
            "turn_profile": "loop",
        },
    )

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["message"] == "loop model readiness failed"
    assert detail["code"] == "loop_readiness_failed"
    assert detail["agents"] == ["cursor"]
    assert "question/tool capability" in detail["reason"]
    assert detail["agent_details"][0]["id"] == "cursor"
    assert detail["agent_details"][0]["loop_blockers"]
    assert not list(tmp_path.iterdir())


def test_room_run_loop_allows_ready_primary_when_substitute_not_loop_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import agent_lab.session as session_mod
    import app.server.deps as deps_mod
    import app.server.routers.room as room_router

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
    monkeypatch.setattr(room_router, "_agents_not_ready", lambda _agents: [])

    captured: dict[str, object] = {}

    def _fake_run_room(topic: str, **kwargs: object) -> tuple[Path, list[object], str]:
        captured["agents"] = kwargs.get("agents")
        folder = tmp_path / "loop-mixed"
        folder.mkdir()
        return folder, [], "# plan"

    monkeypatch.setattr(room_router, "run_room", _fake_run_room)

    from app.server.main import app

    client = TestClient(app)
    res = client.post(
        "/api/room/runs",
        data={
            "topic": "loop mixed roster",
            "agents": '["claude", "kimi_work"]',
            "mode": "plan",
            "synthesize": "true",
            "turn_profile": "loop",
        },
    )

    assert res.status_code == 200
    assert captured["agents"] == ["claude"]


def test_room_run_seeds_room_models_before_first_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import agent_lab.session as session_mod
    import app.server.deps as deps_mod
    import app.server.routers.room as room_router

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(room_router, "_agents_not_ready", lambda _agents: [])

    captured: dict[str, object] = {}

    def _fake_run_room(topic: str, **kwargs: object) -> tuple[Path, list[object], str]:
        folder = kwargs["session_folder"]
        captured["folder"] = folder
        return folder, [], ""

    monkeypatch.setattr(room_router, "run_room", _fake_run_room)

    from app.server.main import app

    client = TestClient(app)
    res = client.post(
        "/api/room/runs",
        data={
            "topic": "pin roster before bind",
            "agents": '["claude", "kimi_work"]',
            "mode": "discuss",
            "room_models": '["kimi_work", "claude"]',
        },
    )

    assert res.status_code == 200
    folder = captured["folder"]
    assert isinstance(folder, Path)
    run_meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run_meta["room_models"] == ["claude", "kimi_work"]
