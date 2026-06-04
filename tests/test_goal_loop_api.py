from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _session(sessions_dir: Path) -> Path:
    folder = sessions_dir / "goal-api"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "topic": "goal api",
                "agents": ["codex"],
                "status": "completed",
                "turns": [],
                "actions": [],
                "approvals": [],
                "executions": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / "chat.jsonl").write_text(
        json.dumps({"role": "agent", "agent": "codex", "content": "GOAL_API_OK"})
        + "\n",
        encoding="utf-8",
    )
    return folder


def test_goal_patch_and_manual_check_api(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sessions_dir = tmp_path / "sessions"
    folder = _session(sessions_dir)
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    monkeypatch.setenv("AGENT_LAB_GOAL_LOOP", "1")
    from app.server.main import app

    client = TestClient(app)
    patch = client.patch(
        "/api/sessions/goal-api/goal",
        json={"text": "대화에 `GOAL_API_OK` 포함", "max_checks": 3},
    )
    check = client.post("/api/sessions/goal-api/goal/check")

    assert patch.status_code == 200
    assert patch.json()["session_goal"]["set_by"] == "human"
    assert patch.json()["goal_loop"]["max_checks"] == 3
    assert check.status_code == 200
    assert check.json()["check"]["verdict"] == "pass"
    assert check.json()["goal_loop"]["status"] == "achieved"
    saved = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert saved["goal_loop"]["status"] == "achieved"


def test_manual_goal_check_requires_feature_flag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sessions_dir = tmp_path / "sessions"
    _session(sessions_dir)
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    monkeypatch.delenv("AGENT_LAB_GOAL_LOOP", raising=False)
    from app.server.main import app

    client = TestClient(app)
    client.patch(
        "/api/sessions/goal-api/goal",
        json={"text": "대화에 `GOAL_API_OK` 포함"},
    )
    response = client.post("/api/sessions/goal-api/goal/check")

    assert response.status_code == 409
    assert response.json()["detail"] == "goal loop is disabled"


def test_goal_patch_rejects_blank_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sessions_dir = tmp_path / "sessions"
    _session(sessions_dir)
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    from app.server.main import app

    response = TestClient(app).patch(
        "/api/sessions/goal-api/goal",
        json={"text": "   "},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "session goal text is required"
