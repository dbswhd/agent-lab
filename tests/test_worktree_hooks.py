"""MB-6 + ABSORB P2 — worktree.yaml setup/verify/create/remove/baseRef/include."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agent_lab.merge_checks import build_merge_checks
from agent_lab.worktree_hooks import (
    apply_worktree_include,
    find_worktree_hooks,
    resolve_include_patterns,
    resolve_worktree_base_ref,
    run_hook_commands,
    run_worktree_create,
    run_worktree_remove,
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


def test_parse_p2_fields_yaml(tmp_path: Path) -> None:
    hooks_dir = tmp_path / ".agent-lab"
    hooks_dir.mkdir()
    (hooks_dir / "worktree.yaml").write_text(
        "\n".join(
            [
                "baseRef: main",
                "include:",
                "  - .env.local",
                "  - secrets/*",
                "create:",
                "  - echo created",
                "remove:",
                "  - echo removed",
                "setup:",
                "  - echo setup",
                "verify:",
                "  - echo verify",
                "",
            ]
        ),
        encoding="utf-8",
    )
    config = find_worktree_hooks(tmp_path)
    assert config is not None
    assert config.base_ref == "main"
    assert config.include == (".env.local", "secrets/*")
    assert config.create == ("echo created",)
    assert config.remove == ("echo removed",)


def test_base_ref_only_config(tmp_path: Path) -> None:
    hooks_dir = tmp_path / ".agent-lab"
    hooks_dir.mkdir()
    (hooks_dir / "worktree.yaml").write_text("baseRef: main\n", encoding="utf-8")
    config = find_worktree_hooks(tmp_path)
    assert config is not None
    assert config.base_ref == "main"
    assert not config.setup


def test_resolve_base_ref_when_git_ref_exists(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    hooks_dir = tmp_path / ".agent-lab"
    hooks_dir.mkdir()
    (hooks_dir / "worktree.yaml").write_text("baseRef: main\n", encoding="utf-8")
    assert resolve_worktree_base_ref(tmp_path) == "main"


def test_include_from_worktreeinclude_file(tmp_path: Path) -> None:
    (tmp_path / ".worktreeinclude").write_text(
        ".env\n# comment\nfoo.txt\n", encoding="utf-8"
    )
    patterns = resolve_include_patterns(tmp_path)
    assert patterns == [".env", "foo.txt"]


def test_apply_worktree_include_copies_file(tmp_path: Path) -> None:
    (tmp_path / ".env.local").write_text("SECRET=1\n", encoding="utf-8")
    hooks_dir = tmp_path / ".agent-lab"
    hooks_dir.mkdir()
    (hooks_dir / "worktree.yaml").write_text(
        "include:\n  - .env.local\n",
        encoding="utf-8",
    )
    wt = tmp_path / "wt"
    wt.mkdir()
    report = apply_worktree_include(git_root=tmp_path, worktree_path=wt)
    assert report["ok"] is True
    assert ".env.local" in report["copied"]
    assert (wt / ".env.local").read_text(encoding="utf-8") == "SECRET=1\n"


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


def test_run_create_and_remove_hooks(tmp_path: Path) -> None:
    hooks_dir = tmp_path / ".agent-lab"
    hooks_dir.mkdir()
    (hooks_dir / "worktree.yaml").write_text(
        "create:\n  - echo created\nremove:\n  - echo removed\n",
        encoding="utf-8",
    )
    worktree = tmp_path / "wt"
    worktree.mkdir()
    create = run_worktree_create(worktree_path=worktree, git_root=tmp_path)
    assert create is not None and create["ok"] is True
    remove = run_worktree_remove(worktree_path=worktree, git_root=tmp_path)
    assert remove is not None and remove["ok"] is True


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


def test_merge_checks_blocks_when_create_failed() -> None:
    run = {
        "executions": [
            {
                "id": "exec-1",
                "status": "pending_approval",
                "isolation_effective": "worktree",
                "worktree_hooks": {
                    "create": {"ok": False, "phase": "create"},
                },
            }
        ]
    }
    payload = build_merge_checks(run)
    hook_check = next(c for c in payload["checks"] if c["id"] == "worktree_hooks")
    assert hook_check["ok"] is False
    assert "create" in hook_check["detail"]
