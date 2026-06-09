"""MB-6 — optional repo worktree setup/verify hooks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.merge_checks import build_merge_checks
from agent_lab.worktree_hooks import (
    find_worktree_hooks,
    run_hook_commands,
    run_worktree_setup,
    run_worktree_verify,
)


def test_find_worktree_hooks_json(tmp_path: Path) -> None:
    hooks_dir = tmp_path / ".agent-lab"
    hooks_dir.mkdir()
    (hooks_dir / "worktree.json").write_text(
        json.dumps({"setup": ["echo setup-ok"], "verify": ["echo verify-ok"]}),
        encoding="utf-8",
    )
    config = find_worktree_hooks(tmp_path)
    assert config is not None
    assert config.setup == ("echo setup-ok",)
    assert config.verify == ("echo verify-ok",)


def test_run_hook_commands_success(tmp_path: Path) -> None:
    report = run_hook_commands(["echo hello"], cwd=tmp_path, phase="setup")
    assert report["ok"] is True
    assert report["results"][0]["exit"] == 0


def test_run_hook_commands_failure(tmp_path: Path) -> None:
    report = run_hook_commands(["exit 3"], cwd=tmp_path, phase="verify")
    assert report["ok"] is False
    assert report["results"][0]["exit"] == 3


def test_run_worktree_setup_and_verify(tmp_path: Path) -> None:
    hooks_dir = tmp_path / ".agent-lab"
    hooks_dir.mkdir()
    (hooks_dir / "worktree.yaml").write_text(
        "setup:\n  - echo setup\nverify:\n  - echo verify\n",
        encoding="utf-8",
    )
    worktree = tmp_path / "wt"
    worktree.mkdir()
    setup = run_worktree_setup(worktree_path=worktree, git_root=tmp_path)
    assert setup is not None
    assert setup["ok"] is True
    verify = run_worktree_verify(worktree_path=worktree, git_root=tmp_path)
    assert verify is not None
    assert verify["ok"] is True


def test_merge_checks_blocks_when_verify_pending() -> None:
    run = {
        "executions": [
            {
                "id": "exec-1",
                "status": "pending_approval",
                "isolation_effective": "worktree",
                "git_root": "/repo",
                "worktree_hooks": {
                    "setup": {
                        "ok": True,
                        "config": {"verify": ["make test"]},
                    }
                },
            }
        ]
    }
    payload = build_merge_checks(run)
    hook_check = next(c for c in payload["checks"] if c["id"] == "worktree_hooks")
    assert hook_check["ok"] is False
    assert payload["merge_disabled"] is True
