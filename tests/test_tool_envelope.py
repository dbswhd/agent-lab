"""G7 — unified tool descriptor + result envelope."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.tool_envelope import (
    ToolDescriptor,
    normalize_tool_result,
    tool_descriptors,
)


# --- pure normalization (no I/O) --------------------------------------------


def _ext(result: dict, *, ok: bool) -> dict:
    return {"ok": ok, "kind": "external", "result": result, "command": {"id": "external:t", "kind": "external"}}


def test_normalize_external_success() -> None:
    raw = _ext({"ok": True, "exit_code": 0, "stdout": "hi", "stderr": ""}, ok=True)
    tr = normalize_tool_result(raw, duration_ms=12.0)
    assert tr.ok and tr.kind == "external" and tr.tool_id == "external:t"
    assert tr.status == "ok" and tr.content == "hi"
    assert tr.data["exit_code"] == 0 and tr.duration_ms == 12.0


def test_normalize_external_pending_human() -> None:
    raw = _ext({"ok": False, "status": "pending_human", "detail": "confirm required"}, ok=False)
    tr = normalize_tool_result(raw)
    assert tr.ok is False and tr.status == "pending_human"
    assert tr.error == "confirm required"


def test_normalize_external_disabled_and_stub() -> None:
    disabled = normalize_tool_result(_ext({"ok": False, "status": "disabled", "detail": "off"}, ok=False))
    assert disabled.ok is False and disabled.status == "disabled"
    stub = normalize_tool_result(_ext({"ok": True, "status": "stub", "detail": "not executed"}, ok=True))
    assert stub.ok is True and stub.status == "stub" and stub.content == "not executed"


def test_normalize_server_goal_check() -> None:
    raw = {"ok": True, "kind": "server", "result": {"verdict": "pass", "detail": "goal met"}, "command": {"id": "goal-check", "kind": "server"}}
    tr = normalize_tool_result(raw)
    assert tr.ok and tr.kind == "server" and tr.content == "goal met"
    assert tr.data["verdict"] == "pass"


def test_normalize_client_and_unknown() -> None:
    client = normalize_tool_result({"ok": True, "kind": "client", "handler": "stop_run", "command": {"id": "stop", "kind": "client"}})
    assert client.ok and client.status == "client_dispatch" and client.content == "stop_run"
    unknown = normalize_tool_result({"ok": False, "detail": "unknown command: x"})
    assert unknown.ok is False and unknown.error == "unknown command: x"


def test_descriptor_from_row_roundtrip() -> None:
    row = {"id": "goal-check", "slash": "/goal-check", "label": "Oracle", "kind": "server", "enabled": False, "disabled_reason": "env_required"}
    d = ToolDescriptor.from_row(row)
    assert d.id == "goal-check" and d.kind == "server"
    assert d.gate() == (False, "env_required")
    assert d.to_dict()["slash"] == "/goal-check"


def test_tool_descriptors_view() -> None:
    catalog = {"commands": [{"id": "a", "kind": "client", "enabled": True}, {"id": "b", "kind": "external", "enabled": False, "disabled_reason": "x"}]}
    ds = tool_descriptors(catalog)
    assert [d.id for d in ds] == ["a", "b"]
    assert ds[1].gate() == (False, "x")


# --- invoke_tool front-door (I/O + trace) -----------------------------------


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "sess-tool"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_invoke_tool_records_trace_span(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_TRACE", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.command_registry import invoke_tool

    # "stop" is a builtin client command — always enabled, no external setup.
    tr = invoke_tool(session_folder, "stop")
    assert tr.ok and tr.kind == "client" and tr.duration_ms is not None
    trace = (session_folder / "trace.jsonl")
    assert trace.is_file()
    spans = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]
    tool_spans = [s for s in spans if s.get("kind") == "tool"]
    assert tool_spans and tool_spans[-1]["name"] == "stop"
    assert tool_spans[-1]["status"] == "client_dispatch"
    assert tool_spans[-1]["dur_ms"] is not None


def test_invoke_tool_trace_off(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TRACE", "0")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.command_registry import invoke_tool

    invoke_tool(session_folder, "stop")
    assert not (session_folder / "trace.jsonl").is_file()


def test_invoke_tool_disabled_gate(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # goal-check requires AGENT_LAB_GOAL_LOOP; unset → disabled.
    monkeypatch.delenv("AGENT_LAB_GOAL_LOOP", raising=False)
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.command_registry import invoke_tool

    tr = invoke_tool(session_folder, "goal-check")
    assert tr.ok is False
    assert tr.error == "env_required"


def test_invoke_tool_external_not_allowlisted(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tools_dir = tmp_path / "lab"
    tools_dir.mkdir()
    (tools_dir / "tools.yaml").write_text("tools:\n  - id: external:t\n    command: echo t\n", encoding="utf-8")
    monkeypatch.setattr("agent_lab.external_tools._tools_paths", lambda: [tools_dir / "tools.yaml"])
    monkeypatch.setenv("AGENT_LAB_EXTERNAL_TOOLS", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.command_registry import invoke_tool

    tr = invoke_tool(session_folder, "external:t")
    assert tr.ok is False
    # disabled at the catalog gate → top-level error envelope.
    assert tr.error == "not_in_session_allowlist"


# --- route exposes envelope --------------------------------------------------


def test_route_returns_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    import agent_lab.session as session_mod
    import app.server.deps as deps_mod
    from app.server.main import app

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "rt"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")

    client = TestClient(app)
    r = client.post(f"/api/sessions/{folder.name}/commands/run", json={"command_id": "stop"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["kind"] == "client"  # raw back-compat keys
    assert body["envelope"]["status"] == "client_dispatch"  # normalized envelope
    assert body["envelope"]["tool_id"] == "stop"
