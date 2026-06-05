"""Command registry and plugin discovery tests."""

from __future__ import annotations

import json
import os
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
    default_allowlist,
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
