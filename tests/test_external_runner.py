from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.command_registry import execute_command, list_commands
from agent_lab.external_tools import _parse_tools_yaml, load_external_tools
from agent_lab.run_meta import read_run_meta
from agent_lab.runtime.external_runner import (
    external_runner_enabled,
    patch_external_tools_allowlist,
    run_external_command,
)
from agent_lab.runtime.snapshot import build_runtime_snapshot


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "sess-ext"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_parse_tools_yaml_list_command() -> None:
    text = """
tools:
  - id: external:echo
    slash: /echo
    label: Echo
    command:
      - echo
      - hello
"""
    rows = _parse_tools_yaml(text)
    assert len(rows) == 1
    assert rows[0]["id"] == "external:echo"
    assert rows[0]["command"] == ["echo", "hello"]


def test_external_runner_disabled_by_default(session_folder: Path) -> None:
    assert external_runner_enabled() is False
    result = run_external_command(session_folder, "external:echo")
    assert result["ok"] is False
    assert result["status"] == "disabled"


def test_external_runner_allowlist_and_confirm(
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tools_dir = tmp_path / "agent-lab-home"
    tools_dir.mkdir()
    (tools_dir / "tools.yaml").write_text(
        """
tools:
  - id: external:echo
    slash: /echo
    label: Echo
    human_approve: true
    command: echo ok
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_EXTERNAL_TOOLS", "1")
    monkeypatch.setattr(
        "agent_lab.external_tools._tools_paths",
        lambda: [tools_dir / "tools.yaml"],
    )

    blocked = run_external_command(session_folder, "external:echo")
    assert blocked["status"] == "not_allowlisted"

    def _allow(run: dict) -> dict:
        return patch_external_tools_allowlist(run, ["external:echo"])

    from agent_lab.run_meta import patch_run_meta

    patch_run_meta(session_folder, _allow)

    pending = run_external_command(session_folder, "external:echo")
    assert pending["status"] == "pending_human"

    result = run_external_command(session_folder, "external:echo", confirm=True)
    assert result["ok"] is True
    assert "ok" in (result.get("stdout") or "")


def test_list_commands_marks_external_disabled(
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tools_dir = tmp_path / "lab"
    tools_dir.mkdir()
    (tools_dir / "tools.yaml").write_text(
        'tools:\n  - id: external:t\n    command: echo t\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("agent_lab.external_tools._tools_paths", lambda: [tools_dir / "tools.yaml"])
    monkeypatch.setenv("AGENT_LAB_EXTERNAL_TOOLS", "1")

    catalog = list_commands(session_folder, mock=True)
    ext = next(c for c in catalog["commands"] if c["id"] == "external:t")
    assert ext["enabled"] is False
    assert ext["disabled_reason"] == "not_in_session_allowlist"


def test_execute_external_via_registry(
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tools_dir = tmp_path / "lab2"
    tools_dir.mkdir()
    (tools_dir / "tools.json").write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "id": "external:json-tool",
                        "slash": "/json-tool",
                        "command": "echo json",
                        "human_approve": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "agent_lab.external_tools._tools_paths",
        lambda: [tools_dir / "tools.json"],
    )
    monkeypatch.setenv("AGENT_LAB_EXTERNAL_TOOLS", "1")

    from agent_lab.run_meta import patch_run_meta

    patch_run_meta(
        session_folder,
        lambda run: patch_external_tools_allowlist(run, ["external:json-tool"]),
    )
    out = execute_command(session_folder, "external:json-tool")
    assert out["ok"] is True
    assert out["kind"] == "external"


def test_snapshot_external_block(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_EXTERNAL_TOOLS", "1")
    snap = build_runtime_snapshot(session_folder)
    assert snap["external"]["runner_enabled"] is True
    assert snap["external"]["allowlist"] == []
