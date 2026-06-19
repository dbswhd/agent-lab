"""Kimi Work workspace.openProject binding (mock)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.kimi_work_workspace import ensure_workspace_bound, resolve_workspace_path


@pytest.fixture(autouse=True)
def _mock_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")


def test_resolve_workspace_path_prefers_permissions(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    bound = tmp_path / "worktree"
    bound.mkdir()
    perms = {"_discuss_cwd": str(bound)}
    assert resolve_workspace_path(perms, session) == bound.resolve()
    assert resolve_workspace_path(None, session) == session.resolve()


def test_ensure_workspace_bound_calls_open_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = tmp_path / "session"
    session.mkdir()
    ws = tmp_path / "repo"
    ws.mkdir()
    calls: list[str] = []

    def _fake_open(path: str | Path) -> dict:
        calls.append(str(path))
        return {"status": "opened"}

    monkeypatch.setattr("agent_lab.kimi_work_workspace.open_workspace", _fake_open)
    ensure_workspace_bound(session, ws)
    ensure_workspace_bound(session, ws)
    assert len(calls) == 1
    assert calls[0] == str(ws.resolve())
    state = (session / "kimi_work.json").read_text(encoding="utf-8")
    assert "workspacePath" in state


def test_open_workspace_falls_back_to_add_entry(tmp_path: Path) -> None:
    from agent_lab.kimi_work_workspace import open_workspace

    ws = tmp_path / "openProject-fail"
    ws.mkdir()
    result = open_workspace(ws)
    assert result["status"] == "added"
    assert result["entry"]["path"] == str(ws.resolve())


def test_ensure_workspace_bound_reopen_on_path_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = tmp_path / "session"
    session.mkdir()
    ws1 = tmp_path / "repo-a"
    ws2 = tmp_path / "repo-b"
    ws1.mkdir()
    ws2.mkdir()
    calls: list[str] = []

    def _fake_open(path: str | Path) -> dict:
        calls.append(str(path))
        return {"status": "opened"}

    monkeypatch.setattr("agent_lab.kimi_work_workspace.open_workspace", _fake_open)
    ensure_workspace_bound(session, ws1)
    ensure_workspace_bound(session, ws2)
    assert calls == [str(ws1.resolve()), str(ws2.resolve())]
