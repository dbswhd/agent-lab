"""Git worktree lifecycle for isolated plan execute (M0 spike)."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_lab.plan_execute_git import (
    default_branch,
    exec_branch_name,
    is_working_tree_clean,
)


class WorktreeUnavailable(Exception):
    """Cannot create isolated worktree."""

    def __init__(self, message: str, *, reason: str = "worktree_unavailable"):
        super().__init__(message)
        self.reason = reason


@dataclass
class ExecWorktree:
    git_root: Path
    worktree_path: Path
    branch: str
    base_branch: str
    base_sha: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "git_root": str(self.git_root.resolve()),
            "worktree_path": str(self.worktree_path.resolve()),
            "exec_branch": self.branch,
            "base_branch": self.base_branch,
            "base_sha": self.base_sha,
        }


def _run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def worktree_dir(session_folder: Path, exec_id: str) -> Path:
    return session_folder / "worktrees" / exec_id


def create_exec_worktree(
    session_folder: Path,
    *,
    exec_id: str,
    git_root: Path,
    action_key: str,
    session_id: str | None = None,
    base_branch: str | None = None,
) -> ExecWorktree:
    """Create branch + worktree; main checkout must stay clean."""
    root = git_root.resolve()
    if not is_working_tree_clean(root):
        raise WorktreeUnavailable(
            f"git root has uncommitted changes: {root}",
            reason="base_branch_dirty",
        )

    branch = exec_branch_name(session_id or session_folder.name, action_key, exec_id)
    base = base_branch or default_branch(root)
    wt_path = worktree_dir(session_folder, exec_id)

    if wt_path.exists():
        shutil.rmtree(wt_path, ignore_errors=True)

    wt_path.parent.mkdir(parents=True, exist_ok=True)

    # Drop stale branch if present
    _run_git(root, "branch", "-D", branch, check=False)

    _run_git(root, "worktree", "add", "-B", branch, str(wt_path), base)
    base_sha = _run_git(root, "rev-parse", base).stdout.strip()

    return ExecWorktree(
        git_root=root,
        worktree_path=wt_path.resolve(),
        branch=branch,
        base_branch=base,
        base_sha=base_sha,
    )


def remove_exec_worktree(
    session_folder: Path,
    *,
    exec_id: str,
    git_root: Path,
    branch: str,
    worktree_path: Path | None = None,
) -> None:
    root = git_root.resolve()
    wt = worktree_path or worktree_dir(session_folder, exec_id)
    if wt.is_dir():
        _run_git(root, "worktree", "remove", "--force", str(wt.resolve()), check=False)
        if wt.exists():
            shutil.rmtree(wt, ignore_errors=True)
    _run_git(root, "worktree", "prune", check=False)
    _run_git(root, "branch", "-D", branch, check=False)


def discard_exec_worktree(ew: ExecWorktree, session_folder: Path, exec_id: str) -> None:
    """Reject path: drop worktree without merging."""
    remove_exec_worktree(
        session_folder,
        exec_id=exec_id,
        git_root=ew.git_root,
        branch=ew.branch,
        worktree_path=ew.worktree_path,
    )
