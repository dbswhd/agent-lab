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
from agent_lab.mission.application import MissionApplication
from agent_lab.mission.kernel import (
    ApproveDiff,
    MarkDiffReady,
    OpenExecutionGate,
    OracleVerdict,
    RecordMerge,
    RecordOracle,
    StartExecution,
)
from agent_lab.run.meta import read_run_meta
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


def test_inbox_api_resolve_rejects_stale_expected_version(
    client: TestClient, session_folder: Path
):
    """§7.3 — a stale ``expected_version`` is a 409 conflict, and the legacy
    ``resolve_inbox_item`` write path never runs (no double-processing)."""
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
    item_id = create.json()["item"]["id"]
    before_run = (session_folder / "run.json").read_bytes()

    stale = client.post(
        f"/api/sessions/{session_id}/inbox/{item_id}/resolve",
        json={"selected": ["two"], "decision": "go", "expected_version": 5},
    )

    assert stale.status_code == 409
    assert "stale answer" in stale.json()["detail"]
    assert (session_folder / "run.json").read_bytes() == before_run

    resolved = client.post(
        f"/api/sessions/{session_id}/inbox/{item_id}/resolve",
        json={"selected": ["two"], "decision": "go", "expected_version": 0},
    )
    assert resolved.status_code == 200
    assert resolved.json()["ok"] is True


def test_inbox_api_resolve_with_expected_version_and_no_decision_field(
    client: TestClient, session_folder: Path
):
    """A plain multi-select answer (no separate `decision` verdict) must still
    succeed when `expected_version` is sent — the guard falls back to
    `selected`/`status` rather than treating it as an empty answer."""
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
    item_id = create.json()["item"]["id"]

    resolved = client.post(
        f"/api/sessions/{session_id}/inbox/{item_id}/resolve",
        json={"selected": ["two"], "expected_version": 0},
    )
    assert resolved.status_code == 200
    assert resolved.json()["ok"] is True


def _make_terminal_mission(folder: Path) -> MissionApplication:
    application = MissionApplication(folder, "inbox test")
    repository = application.repository
    for command in (MarkDiffReady(), ApproveDiff(), RecordMerge("merge")):
        repository.dispatch(command)
    repository.dispatch(RecordOracle(OracleVerdict.PASS, "done"))
    return application


def test_inbox_api_rejects_terminal_orphan_without_mutating_any_store(
    client: TestClient,
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", session_folder.name)
    (session_folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    application = MissionApplication(session_folder, "inbox test")
    application.approve_plan()
    application.repository.dispatch(StartExecution())
    item = create_inbox_item(
        session_folder,
        kind="question",
        source="wave_b",
        prompt="Late?",
        options=[{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}],
    )
    _make_terminal_mission(session_folder)
    before_run = (session_folder / "run.json").read_bytes()
    before_journal = (session_folder / ".agent-lab" / "mission-events.jsonl").read_bytes()

    response = client.post(
        f"/api/sessions/{session_folder.name}/inbox/{item['id']}/resolve",
        json={"selected": ["yes"]},
    )

    assert response.status_code == 409
    assert "terminal_orphan" in response.json()["detail"]
    assert (session_folder / "run.json").read_bytes() == before_run
    assert (session_folder / ".agent-lab" / "mission-events.jsonl").read_bytes() == before_journal


def test_inbox_api_rejects_missing_and_stale_rows_without_closing_gate(
    client: TestClient,
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", session_folder.name)
    (session_folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    application = MissionApplication(session_folder, "inbox test")
    application.approve_plan()
    application.repository.dispatch(StartExecution())
    missing_id = "missing-row"
    application.repository.dispatch(OpenExecutionGate(missing_id, "question", "gone"))
    before_missing = (session_folder / ".agent-lab" / "mission-events.jsonl").read_bytes()

    missing = client.post(
        f"/api/sessions/{session_folder.name}/inbox/{missing_id}/resolve",
        json={"selected": ["yes"]},
    )

    assert missing.status_code == 409
    assert "missing" in missing.json()["detail"]
    assert (session_folder / ".agent-lab" / "mission-events.jsonl").read_bytes() == before_missing

    item = create_inbox_item(
        session_folder,
        kind="question",
        source="wave_b",
        prompt="Old?",
        options=[{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}],
    )
    from agent_lab.run.meta import patch_run_meta

    def mark_stale(run: dict[str, object]) -> dict[str, object]:
        rows = run.get("human_inbox")
        assert isinstance(rows, list)
        for row in rows:
            if isinstance(row, dict) and row.get("id") == item["id"]:
                row["status"] = "resolved"
        return run

    patch_run_meta(session_folder, mark_stale)
    before_stale_run = (session_folder / "run.json").read_bytes()
    before_stale_journal = (session_folder / ".agent-lab" / "mission-events.jsonl").read_bytes()

    stale = client.post(
        f"/api/sessions/{session_folder.name}/inbox/{item['id']}/resolve",
        json={"selected": ["yes"]},
    )

    assert stale.status_code == 409
    assert "stale" in stale.json()["detail"]
    assert (session_folder / "run.json").read_bytes() == before_stale_run
    assert (session_folder / ".agent-lab" / "mission-events.jsonl").read_bytes() == before_stale_journal


def test_build_inbox_mcp_servers(session_folder: Path):
    from agent_lab.cursor.inbox_mcp import build_inbox_mcp_servers

    servers = build_inbox_mcp_servers(session_folder)
    assert "agent-lab-inbox" in servers
    cfg = servers["agent-lab-inbox"]
    assert "-m" in cfg.args
    assert "agent_lab.inbox.mcp_server" in cfg.args
    assert cfg.env.get("AGENT_LAB_SESSION_FOLDER") == str(session_folder.resolve())


def test_build_codex_inbox_mcp_config_args(session_folder: Path):
    import sys

    from agent_lab.cursor.inbox_mcp import (
        INBOX_MCP_SERVER_NAME,
        build_codex_inbox_mcp_config_args,
    )

    args = build_codex_inbox_mcp_config_args(session_folder)
    assert args.count("-c") >= 4
    joined = " ".join(args)
    assert INBOX_MCP_SERVER_NAME in joined
    assert "agent_lab.inbox.mcp_server" in joined
    assert sys.executable in joined
    assert str(session_folder.resolve()) in joined


def test_build_claude_inbox_mcp_overlay(session_folder: Path):
    import json

    from agent_lab.cursor.inbox_mcp import (
        INBOX_MCP_SERVER_NAME,
        build_claude_inbox_mcp_overlay,
    )

    overlay = build_claude_inbox_mcp_overlay(session_folder)
    data = json.loads(overlay.read_text(encoding="utf-8"))
    entry = data["mcpServers"][INBOX_MCP_SERVER_NAME]
    assert "agent_lab.inbox.mcp_server" in entry["args"]
    assert entry["env"]["AGENT_LAB_SESSION_FOLDER"] == str(session_folder.resolve())


def test_resolve_claude_mcp_config_inbox_overlay(tmp_path: Path):
    import json

    from agent_lab.claude.cli import _resolve_claude_mcp_config
    from agent_lab.cursor.inbox_mcp import INBOX_MCP_SERVER_NAME

    sess = tmp_path / "sess"
    sess.mkdir()
    cfg = _resolve_claude_mcp_config(sess, {}, inbox_mcp=True)
    assert cfg is not None
    data = json.loads(Path(cfg).read_text(encoding="utf-8"))
    assert INBOX_MCP_SERVER_NAME in data["mcpServers"]


def test_call_agent_reply_passes_inbox_mcp_to_claude(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.agents.registry import call_agent_reply

    captured: dict[str, object] = {}

    def _fake_claude(_system: str, _user: str, **kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    monkeypatch.setattr("agent_lab.agents.registry._is_ready", lambda _a: True)
    monkeypatch.setattr("agent_lab.agents.claude_agent.respond", _fake_claude)
    call_agent_reply("claude", "", "hi", inbox_mcp=True)
    assert captured.get("inbox_mcp") is True


def test_execute_inbox_mcp_enabled_env(monkeypatch: pytest.MonkeyPatch):
    from agent_lab.cursor.inbox_mcp import execute_inbox_mcp_enabled

    monkeypatch.delenv("AGENT_LAB_EXECUTE_INBOX", raising=False)
    assert execute_inbox_mcp_enabled() is True
    monkeypatch.setenv("AGENT_LAB_EXECUTE_INBOX", "0")
    assert execute_inbox_mcp_enabled() is False


def test_mount_inbox_mcp_plan_lane_when_execute_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.cursor.inbox_mcp import mount_inbox_mcp_when_requested

    monkeypatch.setenv("AGENT_LAB_EXECUTE_INBOX", "0")
    monkeypatch.setenv("AGENT_LAB_PLAN_INBOX", "1")
    assert mount_inbox_mcp_when_requested(True) is True
    assert mount_inbox_mcp_when_requested(False) is False
    monkeypatch.setenv("AGENT_LAB_PLAN_INBOX", "0")
    assert mount_inbox_mcp_when_requested(True) is False


def test_codex_invoke_uses_plan_inbox_when_execute_off(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_EXECUTE_INBOX", "0")
    monkeypatch.setenv("AGENT_LAB_PLAN_INBOX", "1")
    out_path = tmp_path / "codex-out.txt"
    captured: dict[str, object] = {}

    monkeypatch.setattr("agent_lab.codex.cli.tempfile.mktemp", lambda **_k: str(out_path))

    def _fake_build_cmd(**kwargs):
        captured["config_overrides"] = kwargs.get("config_overrides")
        return ["codex", "exec"]

    def _fake_run_codex(_cmd, _prompt, **_kwargs):
        out_path.write_text("done", encoding="utf-8")
        from agent_lab.codex.cli import CodexRunOutcome

        return CodexRunOutcome()

    monkeypatch.setattr("agent_lab.codex.cli._build_cmd", _fake_build_cmd)
    monkeypatch.setattr("agent_lab.codex.cli._run_codex", _fake_run_codex)
    monkeypatch.setattr("agent_lab.codex.cli.resolve_codex_bin", lambda: "/bin/codex")
    monkeypatch.setattr(
        "agent_lab.runtime.adapters.codex.can_route_codex_proxy",
        lambda **_k: False,
    )
    monkeypatch.setattr(
        "agent_lab.agent.hooks_materializer.native_agent_hooks_overlay",
        lambda *_a, **_k: __import__("contextlib").nullcontext(),
    )

    from agent_lab.codex.cli import invoke

    text = invoke("sys", "user", session_folder=tmp_path, inbox_mcp=True, room_turn=True)
    assert text == "done"
    assert captured.get("config_overrides") is not None


def test_call_execute_agent_passes_inbox_mcp_to_codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from agent_lab.plan.execute import _call_execute_agent

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
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "1")
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
        item.get("trigger") == "T-Q0" and item.get("status") == "pending" for item in run.get("human_inbox") or []
    )


def test_inbox_settings_api(client: TestClient, session_folder: Path, monkeypatch: pytest.MonkeyPatch):
    session_id = session_folder.name
    monkeypatch.delenv("AGENT_LAB_INBOX_MODE", raising=False)

    get_res = client.get(f"/api/sessions/{session_id}/inbox/settings")
    assert get_res.status_code == 200
    get_body = get_res.json()
    assert get_body["ok"] is True
    assert get_body["inbox_mode"] == "sync"

    patch_res = client.patch(
        f"/api/sessions/{session_id}/inbox/settings",
        json={"inbox_mode": "soft"},
    )
    assert patch_res.status_code == 200
    patch_body = patch_res.json()
    assert patch_body["inbox_mode"] == "soft"
    assert patch_body["session_override"] == "soft"

    run = read_run_meta(session_folder)
    assert run.get("inbox_mode") == "soft"
