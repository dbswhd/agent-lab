"""Mission OS Phase 2 — gate_scope, router, Telegram adapter."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.gate_scope import (
    compute_gate_scope,
    get_gate_profile,
    should_pause_discuss_for_profile,
)
from agent_lab.gateway.router import route_inbound
from agent_lab.gateway.telegram_adapter import handle_gateway_command
from agent_lab.human_inbox import create_inbox_item
from agent_lab.inbox.harvest import should_pause_discuss
from agent_lab.run.meta import read_run_meta
from app.server.main import app


def _pause_eligible_question(**extra: object) -> dict:
    base = {
        "id": "q1",
        "kind": "question",
        "status": "pending",
        "trigger": "T-Q1",
        "options": [
            {"id": "a", "label": "A"},
            {"id": "b", "label": "B"},
        ],
    }
    base.update(extra)
    return base


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    folder = tmp_path / "gw-sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("gw\n", encoding="utf-8")
    (folder / "run.json").write_text('{"gate_profile":"assistant"}', encoding="utf-8")
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    return folder


def test_gate_profile_defaults_dev() -> None:
    assert get_gate_profile({}) == "dev"
    assert get_gate_profile({"gate_profile": "assistant"}) == "assistant"


def test_assistant_soft_discuss_with_pending_question() -> None:
    run = {
        "gate_profile": "assistant",
        "human_inbox": [_pause_eligible_question(prompt="Scope?")],
    }
    scope = compute_gate_scope(run)
    assert scope.discuss_rounds == "allow"
    assert scope.plan_workflow == "block_clarify"
    assert should_pause_discuss_for_profile(run) is False


def test_assistant_ignores_legacy_optionless_question() -> None:
    run = {
        "gate_profile": "assistant",
        "human_inbox": [
            {
                "id": "q1",
                "kind": "question",
                "status": "pending",
                "trigger": "T-Q1",
                "options": [],
                "prompt": "Scope?",
            }
        ],
    }
    scope = compute_gate_scope(run)
    assert scope.plan_workflow == "allow"


def test_dev_pause_discuss_with_pending_question() -> None:
    run = {
        "gate_profile": "dev",
        "human_inbox": [_pause_eligible_question(prompt="Scope?")],
    }
    scope = compute_gate_scope(run)
    assert scope.discuss_rounds == "pause"
    assert should_pause_discuss(run) is True


def test_routes_toml_prefix_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    routes = tmp_path / "routes.toml"
    routes.write_text(
        """
[[route]]
match = { channel = "telegram", prefix = "/dev" }
session_id = "agent-lab-dev"
gate_profile = "dev"

[default]
session_id = "assistant-home"
gate_profile = "assistant"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_ROUTES_CONFIG", str(routes))
    routed = route_inbound(channel="telegram", text="/dev /status")
    assert routed["session_id"] == "agent-lab-dev"
    assert routed["gate_profile"] == "dev"
    assert routed["text"] == "/status"
    default = route_inbound(channel="telegram", text="hello")
    assert default["session_id"] == "assistant-home"


def test_gateway_routes_api(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    routes = tmp_path / "routes.toml"
    routes.write_text('[default]\nsession_id = "home"\ngate_profile = "assistant"\n', encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_ROUTES_CONFIG", str(routes))
    r = client.get("/api/gateway/routes")
    assert r.status_code == 200
    assert r.json()["default"]["session_id"] == "home"


def test_inbound_webhook_route(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    routes = tmp_path / "routes.toml"
    routes.write_text(
        """
[[route]]
match = { channel = "webhook", hook_id = "github-ci" }
session_id = "ci-triage"
gate_profile = "assistant"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_ROUTES_CONFIG", str(routes))
    r = client.post("/api/hooks/github-ci", json={"text": "build failed"})
    assert r.status_code == 200
    assert r.json()["route"]["session_id"] == "ci-triage"


def test_telegram_resolve_command(session_folder: Path) -> None:
    item = create_inbox_item(
        session_folder,
        kind="question",
        source="manual",
        prompt="Pick?",
        options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
    )
    result = handle_gateway_command(
        session_id=session_folder.name,
        text=f"/resolve {item['id']} a",
        gate_profile="assistant",
    )
    assert result["ok"] is True
    run = read_run_meta(session_folder)
    assert run["human_inbox"][0]["status"] == "resolved"


def test_telegram_webhook_mock_send(
    client: TestClient,
    session_folder: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gw = tmp_path / "gateway.toml"
    gw.write_text(
        """
[telegram]
enabled = true
bot_token = "test-token"
allowed_chat_ids = [12345]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    routes = tmp_path / "routes.toml"
    routes.write_text(
        f'[default]\nsession_id = "{session_folder.name}"\ngate_profile = "assistant"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_GATEWAY_CONFIG", str(gw))
    monkeypatch.setenv("AGENT_LAB_ROUTES_CONFIG", str(routes))

    sent: list[dict] = []

    def _fake_send(chat_id, text, **kwargs):
        sent.append({"chat_id": chat_id, "text": text})
        return {"ok": True}

    monkeypatch.setattr(
        "agent_lab.gateway.telegram_adapter.send_telegram_message",
        _fake_send,
    )

    update = {
        "message": {
            "chat": {"id": 12345},
            "text": "/status",
        }
    }
    r = client.post("/api/gateway/telegram/webhook", json=update)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert sent
    assert session_folder.name in sent[0]["text"]


def test_runtime_gates_include_gate_scope(client: TestClient, session_folder: Path) -> None:
    create_inbox_item(
        session_folder,
        kind="build",
        source="mcp_propose_build",
        prompt="GO?",
        summary="build",
    )
    r = client.get(f"/api/sessions/{session_folder.name}/runtime")
    assert r.status_code == 200
    gates = r.json()["gates"]
    assert gates.get("gate_profile") == "assistant"
    assert gates.get("execute", {}).get("open") is False
