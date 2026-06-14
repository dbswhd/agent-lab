"""API routes for commands and plugins."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.server.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_GOAL_LOOP", "1")


def test_get_commands(client: TestClient, mock_env: None):
    res = client.get("/api/commands")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert any(c["id"] == "goal-check" for c in body["commands"])


def test_get_agents_plugins(client: TestClient, mock_env: None):
    res = client.get("/api/agents/plugins")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "plugins" in body


def test_session_plugin_allowlist_and_command_run(
    client: TestClient,
    mock_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from agent_lab import session as session_mod
    import app.server.deps as deps_mod

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "2026-06-05-cmd-test"
    folder.mkdir()
    (folder / "topic.txt").write_text("cmd test", encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")

    plugins = client.get(f"/api/agents/plugins?session_id={folder.name}").json()
    first = plugins["plugins"][0]["id"]

    patch = client.patch(
        f"/api/sessions/{folder.name}/agent-plugins",
        json={"agent": plugins["plugins"][0]["agent"], "enabled": [first]},
    )
    assert patch.status_code == 200

    from agent_lab.goal_loop import set_session_goal

    set_session_goal(folder, "use `GOAL_OK`")
    (folder / "chat.jsonl").write_text(
        json.dumps({"role": "agent", "content": "GOAL_OK"}) + "\n",
        encoding="utf-8",
    )
    run = client.post(
        f"/api/sessions/{folder.name}/commands/run",
        json={"command_id": "goal-check"},
    )
    assert run.status_code == 200
    assert run.json()["kind"] == "server"


def test_patch_external_tools_allowlist(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from agent_lab import session as session_mod
    import app.server.deps as deps_mod

    tools_dir = tmp_path / "home" / ".agent-lab"
    tools_dir.mkdir(parents=True)
    (tools_dir / "tools.yaml").write_text(
        "tools:\n  - id: external:echo\n    command: echo ok\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_EXTERNAL_TOOLS", "1")
    monkeypatch.setattr(
        "agent_lab.external_tools._tools_paths",
        lambda: [tools_dir / "tools.yaml"],
    )

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path / "sessions")
    folder = tmp_path / "sessions" / "ext-allow"
    folder.mkdir(parents=True)
    (folder / "topic.txt").write_text("ext", encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")

    patch = client.patch(
        f"/api/sessions/{folder.name}/external-tools",
        json={"enabled": ["external:echo"]},
    )
    assert patch.status_code == 200
    body = patch.json()
    assert body["ok"] is True
    assert "external:echo" in (body.get("external_tools") or {}).get("allowlist", [])

    blocked = client.post(
        f"/api/sessions/{folder.name}/commands/run",
        json={"command_id": "external:echo"},
    )
    assert blocked.status_code == 409

    run = client.post(
        f"/api/sessions/{folder.name}/commands/run",
        json={"command_id": "external:echo", "confirm": True},
    )
    assert run.status_code == 200
    assert run.json()["kind"] == "external"
