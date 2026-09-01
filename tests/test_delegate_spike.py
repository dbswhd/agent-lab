"""Delegate spike — worktree cwd + handoff attach (mock-only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.external_handoff import public_external_handoff, try_attach_handoff_from_external_result
from agent_lab.external_tools import (
    load_external_tools,
    resolve_external_tool_cwd,
    run_external_tool,
)
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.runtime.external_runner import (
    patch_external_tools_allowlist,
    run_external_command,
)


def _pending_worktree_execution(
    folder: Path,
    *,
    execution_id: str = "exec-delegate-1",
    worktree_path: Path,
) -> None:
    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "executions": [
                {
                    "id": execution_id,
                    "status": "pending_approval",
                    "action_index": 1,
                    "isolation_effective": "worktree",
                    "worktree_path": str(worktree_path),
                    "git_root": str(worktree_path.parent),
                    "exec_branch": "agent-lab/delegate-fixture",
                    "base_branch": "main",
                    "base_sha": "0" * 40,
                }
            ],
            "external_tools": {"enabled": ["external:codex-delegate"]},
        },
    )


def test_default_catalog_includes_delegate_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent_lab.external_tools._tools_paths", lambda: [])
    ids = {row["id"] for row in load_external_tools()}
    assert "external:codex-delegate" in ids
    assert "external:claude-delegate" in ids


def test_resolve_worktree_cwd_from_pending_execution(tmp_path: Path) -> None:
    session = tmp_path / "sess-wt"
    session.mkdir()
    worktree = tmp_path / "wt-root"
    worktree.mkdir()
    (session / "run.json").write_text("{}", encoding="utf-8")
    _pending_worktree_execution(session, worktree_path=worktree)

    cwd, err = resolve_external_tool_cwd(
        cwd_mode="worktree",
        session_folder=session,
    )
    assert err is None
    assert cwd == worktree


def test_resolve_worktree_cwd_errors_without_pending(tmp_path: Path) -> None:
    session = tmp_path / "sess-empty"
    session.mkdir()
    (session / "run.json").write_text("{}", encoding="utf-8")

    cwd, err = resolve_external_tool_cwd(
        cwd_mode="worktree",
        session_folder=session,
    )
    assert cwd is None
    assert err == "no open execution for worktree cwd"


def test_run_external_tool_worktree_cwd_and_handoff_attach(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = tmp_path / "sess-delegate"
    session.mkdir()
    worktree = tmp_path / "exec-wt"
    worktree.mkdir()
    (session / "run.json").write_text("{}", encoding="utf-8")
    _pending_worktree_execution(session, worktree_path=worktree)

    handoff = {
        "stopped_cleanly": True,
        "changed_files": ["src/delegate.py"],
        "checks": [{"cmd": "make test-fast", "exit": 0}],
        "evidence_summary": "delegate mock complete",
        "risks": [],
    }
    tools_dir = tmp_path / "tools-home"
    tools_dir.mkdir()
    (tools_dir / "tools.yaml").write_text(
        f"""
tools:
  - id: external:codex-delegate
    slash: /codex-delegate
    label: Codex delegate mock
    human_approve: false
    cwd: worktree
    command: echo '{json.dumps(handoff)}'
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "agent_lab.external_tools._tools_paths",
        lambda: [tools_dir / "tools.yaml"],
    )

    result = run_external_tool(
        "external:codex-delegate",
        session_folder=session,
        args="fix the bug",
    )
    assert result.get("ok") is True
    assert "delegate mock complete" in (result.get("stdout") or "")

    attached = try_attach_handoff_from_external_result(
        session,
        result,
        tool_id="external:codex-delegate",
    )
    assert attached is not None
    assert attached.get("attached") is True
    assert attached.get("execution_id") == "exec-delegate-1"

    run = read_run_meta(session)
    handoff_row = public_external_handoff(run["executions"][0])
    assert handoff_row is not None
    assert handoff_row["evidence_summary"] == "delegate mock complete"
    assert handoff_row.get("tool_id") == "external:codex-delegate"


def test_run_external_command_worktree_cwd_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = tmp_path / "sess-no-wt"
    session.mkdir()
    (session / "run.json").write_text("{}", encoding="utf-8")

    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "tools.yaml").write_text(
        """
tools:
  - id: external:codex-delegate
    command: echo hi
    human_approve: false
    cwd: worktree
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_EXTERNAL_TOOLS", "1")
    monkeypatch.setattr(
        "agent_lab.external_tools._tools_paths",
        lambda: [tools_dir / "tools.yaml"],
    )
    patch_run_meta(
        session,
        lambda run: patch_external_tools_allowlist(run, ["external:codex-delegate"]),
    )

    result = run_external_command(session, "external:codex-delegate", confirm=True)
    assert result.get("ok") is False
    assert result.get("status") == "worktree_cwd_unavailable"


def test_worktree_path_placeholder_expanded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = tmp_path / "sess-ph"
    session.mkdir()
    worktree = tmp_path / "wt-ph"
    worktree.mkdir()
    (session / "run.json").write_text("{}", encoding="utf-8")
    _pending_worktree_execution(session, worktree_path=worktree, execution_id="exec-ph")

    tools_dir = tmp_path / "tools-ph"
    tools_dir.mkdir()
    (tools_dir / "tools.yaml").write_text(
        """
tools:
  - id: external:path-probe
    command: /bin/sh -c 'echo worktree={worktree_path}'
    human_approve: false
    cwd: worktree
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "agent_lab.external_tools._tools_paths",
        lambda: [tools_dir / "tools.yaml"],
    )

    result = run_external_tool("external:path-probe", session_folder=session)
    assert result.get("ok") is True
    assert f"worktree={worktree}" in (result.get("stdout") or "")
