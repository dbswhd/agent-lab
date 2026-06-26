"""Command registry and plugin discovery tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from agent_lab.command_registry import (
    execute_command,
    find_command,
    list_commands,
    parse_slash_command,
)
from agent_lab.goal_loop import set_session_goal
from agent_lab.plugin_discovery import (
    discover_plugins,
    merge_session_allowlist,
    patch_agent_plugins,
    scan_skills,
)


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_GOAL_LOOP", "1")


def test_scan_skills_finds_repo_skills():
    root = Path(__file__).resolve().parents[1]
    skills = scan_skills(root)
    names = {s["name"] for s in skills}
    assert "smoke-and-score" in names


def test_discover_plugins_mock_mode(mock_env: None):
    root = Path(__file__).resolve().parents[1]
    payload = discover_plugins(root, mock=True)
    assert payload["mock"] is True
    assert any(p["agent"] == "codex" for p in payload["plugins"])
    assert any(p["agent"] == "cursor" for p in payload["plugins"])


def test_list_commands_includes_builtin_and_plugins(mock_env: None, tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    catalog = list_commands(folder, workspace=Path(__file__).resolve().parents[1], mock=True)
    ids = {c["id"] for c in catalog["commands"]}
    assert "goal-check" in ids
    assert any(c.get("kind") == "plugin" or c.get("kind") == "agent_invoke" for c in catalog["commands"])


def test_parse_slash_command():
    assert parse_slash_command("/goal-check") == ("goal-check", "")
    assert parse_slash_command("/smoke-and-score extra") == ("smoke-and-score", "extra")
    assert parse_slash_command("hello") is None


def test_merge_session_allowlist_defaults(mock_env: None):
    plugins = discover_plugins(Path(__file__).resolve().parents[1], mock=True)["plugins"]
    allow = merge_session_allowlist({}, plugins)
    assert allow["claude"]


def test_patch_agent_plugins_round_trip():
    run: dict = {}
    patch_agent_plugins(run, "claude", ["a", "b"])
    assert run["agent_plugins"]["claude"]["enabled"] == ["a", "b"]


def test_execute_goal_check_command(mock_env: None, tmp_path: Path):
    folder = tmp_path / "sess"
    folder.mkdir()
    set_session_goal(folder, "record `GOAL_OK` in transcript")
    (folder / "chat.jsonl").write_text(
        json.dumps({"role": "agent", "content": "done GOAL_OK"}) + "\n",
        encoding="utf-8",
    )
    catalog = list_commands(folder, mock=True)
    cmd = find_command(catalog, "goal-check")
    assert cmd is not None
    result = execute_command(folder, "goal-check", workspace=Path(__file__).resolve().parents[1])
    assert result["ok"] is True
    assert result["kind"] == "server"


def test_logout_command_returns_auth_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "0")
    chat = tmp_path / "chat.jsonl"
    chat.write_text("", encoding="utf-8")
    result = execute_command(tmp_path, "logout", args="codex")
    assert result["ok"] is True
    auth_run = result["result"]["auth_run"]
    assert auth_run["provider_id"] == "codex"
    assert auth_run["action"] == "logout"
    assert chat.read_text(encoding="utf-8").strip() == ""
    from agent_lab.auth_runs import get_auth_run

    run = get_auth_run(auth_run["id"])
    assert run is not None
    deadline = time.monotonic() + 2.0
    while run.status == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    lines = chat.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert "/logout codex:" in payload["content"]
    assert "시작" not in payload["content"]
