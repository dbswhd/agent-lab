"""Human Inbox — run.json items and API."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.human_inbox import (
    create_inbox_item,
    format_human_decision,
    has_pending_question,
    resolve_inbox_item,
    supersede_pending_inbox,
    wait_for_inbox_item,
)
from agent_lab.run_meta import read_run_meta
from app.server.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from agent_lab import session as session_mod
    import app.server.deps as deps_mod

    folder = tmp_path / "sess-inbox-1"
    folder.mkdir()
    (folder / "topic.txt").write_text("inbox test\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    return folder


def test_create_and_resolve_question(session_folder: Path):
    item = create_inbox_item(
        session_folder,
        kind="question",
        source="manual",
        prompt="Scope?",
        options=[
            {"id": "a", "label": "A"},
            {"id": "b", "label": "B"},
        ],
    )
    assert item["status"] == "pending"
    run = read_run_meta(session_folder)
    assert run.get("inbox_pending") is True

    resolved = resolve_inbox_item(
        session_folder,
        item["id"],
        selected=["a"],
    )
    assert resolved["status"] == "resolved"
    assert resolved["resolved_selected"] == ["a"]
    line = format_human_decision(resolved)
    assert line.startswith("[HUMAN-DECISION:")
    assert "choice=a" in line.replace(" ", "")

    chat_lines = (session_folder / "chat.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(chat_lines) == 1
    record = json.loads(chat_lines[0])
    assert record["role"] == "human"
    assert "[HUMAN-DECISION:" in record["content"]


def test_build_blocked_by_pending_question(session_folder: Path):
    create_inbox_item(
        session_folder,
        kind="question",
        source="manual",
        prompt="Q?",
        options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
    )
    assert has_pending_question(read_run_meta(session_folder))
    with pytest.raises(ValueError, match="pending question blocks"):
        create_inbox_item(
            session_folder,
            kind="build",
            source="manual",
            prompt="Go?",
            summary="Run it",
            action_ref="now:1",
        )


def test_supersede_on_new_human_turn(session_folder: Path):
    item = create_inbox_item(
        session_folder,
        kind="question",
        source="orchestrator",
        prompt="Old?",
        options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
    )
    count = supersede_pending_inbox(session_folder, human_turn_id=3)
    assert count == 1
    run = read_run_meta(session_folder)
    stored = run["human_inbox"][0]
    assert stored["id"] == item["id"]
    assert stored["status"] == "superseded"
    assert run.get("inbox_pending") is False


def test_wait_for_inbox_item_resolves(session_folder: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_INBOX_POLL_SEC", "0.05")
    item = create_inbox_item(
        session_folder,
        kind="question",
        source="mcp_ask_human",
        prompt="Pick",
        options=[{"id": "x", "label": "X"}, {"id": "y", "label": "Y"}],
    )

    def _resolve_later() -> None:
        resolve_inbox_item(session_folder, item["id"], selected=["y"], append_chat=False)

    threading.Timer(0.15, _resolve_later).start()
    result = wait_for_inbox_item(session_folder, item["id"], timeout_sec=2)
    assert result["selected"] == ["y"]


def test_inbox_summary_api(client: TestClient, session_folder: Path):
    session_id = session_folder.name
    create_inbox_item(
        session_folder,
        kind="question",
        source="manual",
        prompt="Pick?",
        options=[
            {"id": "a", "label": "A"},
            {"id": "b", "label": "B"},
        ],
    )

    summary = client.get("/api/inbox/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["ok"] is True
    assert body["total_pending"] == 1
    assert body["pending_questions"] == 1
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["session_id"] == session_id


def test_inbox_api_resolve(client: TestClient, session_folder: Path):
    session_id = session_folder.name
    create = client.post(
        f"/api/sessions/{session_id}/inbox/items",
        json={
            "kind": "question",
            "prompt": "Pick one",
            "options": [
                {"id": "one", "label": "One"},
                {"id": "two", "label": "Two"},
            ],
        },
    )
    assert create.status_code == 200
    item_id = create.json()["item"]["id"]

    resolved = client.post(
        f"/api/sessions/{session_id}/inbox/{item_id}/resolve",
        json={"selected": ["two"]},
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["ok"] is True
    assert body["inbox_pending"] is False
    assert "human_decision" in body


def test_build_inbox_mcp_servers(session_folder: Path):
    from agent_lab.cursor_inbox_mcp import build_inbox_mcp_servers

    servers = build_inbox_mcp_servers(session_folder)
    assert "agent-lab-inbox" in servers
    cfg = servers["agent-lab-inbox"]
    assert "-m" in cfg.args
    assert "agent_lab.inbox_mcp_server" in cfg.args
    assert cfg.env.get("AGENT_LAB_SESSION_FOLDER") == str(session_folder.resolve())


def test_build_codex_inbox_mcp_config_args(session_folder: Path):
    import sys

    from agent_lab.cursor_inbox_mcp import (
        INBOX_MCP_SERVER_NAME,
        build_codex_inbox_mcp_config_args,
    )

    args = build_codex_inbox_mcp_config_args(session_folder)
    assert args.count("-c") >= 4
    joined = " ".join(args)
    assert INBOX_MCP_SERVER_NAME in joined
    assert "agent_lab.inbox_mcp_server" in joined
    assert sys.executable in joined
    assert str(session_folder.resolve()) in joined


def test_execute_inbox_mcp_enabled_env(monkeypatch: pytest.MonkeyPatch):
    from agent_lab.cursor_inbox_mcp import execute_inbox_mcp_enabled

    monkeypatch.delenv("AGENT_LAB_EXECUTE_INBOX", raising=False)
    assert execute_inbox_mcp_enabled() is True
    monkeypatch.setenv("AGENT_LAB_EXECUTE_INBOX", "0")
    assert execute_inbox_mcp_enabled() is False


def test_call_execute_agent_passes_inbox_mcp_to_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agent_lab.plan_execute import _call_execute_agent

    captured: dict[str, object] = {}

    def _respond(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("agent_lab.agents.codex_agent.respond", _respond)
    out = _call_execute_agent(
        "codex",
        user="do work",
        permissions={},
        cwd=tmp_path,
        on_activity=None,
        verify="none",
        session_folder=tmp_path / "sess",
        inbox_mcp=True,
    )
    assert out == "ok"
    assert captured.get("inbox_mcp") is True
    assert captured.get("session_folder") == tmp_path / "sess"


def test_resolve_question_freeform_note(session_folder: Path):
    item = create_inbox_item(
        session_folder,
        kind="question",
        source="orchestrator",
        prompt="Harvested direction?",
        options=[],
        trigger="T-Q1",
    )
    resolved = resolve_inbox_item(
        session_folder,
        item["id"],
        note="Prefer VU-only scope",
        append_chat=False,
    )
    assert resolved["resolved_choice"] == "freeform"
    assert resolved["resolved_note"] == "Prefer VU-only scope"
    line = format_human_decision(resolved)
    assert "choice=freeform" in line.replace(" ", "")
    assert "Prefer VU-only scope" in line


def test_complete_sse_inbox_pending_on_clarifier(monkeypatch, tmp_path):
    from agent_lab import room

    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "1")
    events: list[tuple[str, dict]] = []

    folder, _messages, _plan_md = room.run_room(
        "short topic",
        agents=["cursor"],
        synthesize=False,
        parallel_rounds=1,
        sessions_base=tmp_path,
        on_event=lambda typ, payload: events.append((typ, payload)),
    )

    complete = [payload for typ, payload in events if typ == "complete"][-1]
    assert complete.get("inbox_pending") is True

    run = read_run_meta(folder)
    assert run.get("inbox_pending") is True
    assert any(
        item.get("trigger") == "T-Q0" and item.get("status") == "pending"
        for item in run.get("human_inbox") or []
    )
