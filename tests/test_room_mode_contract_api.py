from __future__ import annotations

from pathlib import Path

import pytest


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
    assert detail["agents"] == ["cursor"]
    assert "question/tool capability" in detail["reason"]
    assert not list(tmp_path.iterdir())
