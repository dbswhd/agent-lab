"""Fast-tier API smoke tests using create_app factory (no import-time bootstrap)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_id = "smoke-session"
    session_dir = sessions_dir / session_id
    session_dir.mkdir()
    (session_dir / "run.json").write_text("{}", encoding="utf-8")
    (session_dir / "topic.txt").write_text("smoke\n", encoding="utf-8")

    import agent_lab.session.paths as sp

    monkeypatch.setattr(sp, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr("app.server.session_helpers.SESSIONS_DIR", sessions_dir)

    from app.server.main import create_app

    return TestClient(create_app(bootstrap=False))


@pytest.mark.fast
def test_health_smoke(api_client: TestClient) -> None:
    res = api_client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True


@pytest.mark.fast
def test_room_run_lock_smoke(api_client: TestClient) -> None:
    res = api_client.get("/api/room/run-lock")
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    assert set(body) >= {"locked", "active_workers", "age_sec"}


@pytest.mark.fast
def test_execute_dry_run_shape(api_client: TestClient) -> None:
    res = api_client.post(
        "/api/sessions/smoke-session/execute/dry-run",
        json={"action_index": 1, "permissions": {}},
    )
    assert res.status_code in (400, 404, 409, 503)
    detail = res.json().get("detail")
    assert detail is not None


@pytest.mark.fast
def test_create_app_factory_without_bootstrap() -> None:
    from app.server.main import create_app

    app = create_app(bootstrap=False)
    assert app.title == "Agent Lab API"
