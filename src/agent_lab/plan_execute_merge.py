"""In-product merge for worktree executions (M0 spike)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agent_lab.plan_execute_git import is_working_tree_clean
from agent_lab.plan_execute_worktree import ExecWorktree, remove_exec_worktree


class MergeConflict(Exception):
    def __init__(self, message: str, *, conflict_files: list[str]):
        super().__init__(message)
        self.conflict_files = conflict_files


@dataclass
class MergeResult:
    status: Literal["merged", "conflict"]
    commit_sha: str | None
    conflict_files: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "commit_sha": self.commit_sha,
            "conflict_files": self.conflict_files,
        }


def _run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def merge_exec_branch(
    ew: ExecWorktree,
    *,
    session_folder: Path,
    exec_id: str,
    message: str | None = None,
    squash: bool = False,
) -> MergeResult:
    """Merge exec branch into base branch at git_root; remove worktree on success."""
    root = ew.git_root.resolve()
    if not is_working_tree_clean(root):
        raise ValueError("base branch working tree must be clean before merge")

    msg = message or f"agent-lab: merge {ew.branch}"

    if squash:
        _run_git(root, "merge", "--squash", ew.branch)
        if not is_working_tree_clean(root):
            _run_git(root, "commit", "-m", msg)
    else:
        try:
            _run_git(root, "merge", "--no-ff", ew.branch, "-m", msg)
        except subprocess.CalledProcessError:
            conflict_files = _list_conflicts(root)
            _run_git(root, "merge", "--abort", check=False)
            raise MergeConflict("merge conflict", conflict_files=conflict_files)

    sha = _run_git(root, "rev-parse", "HEAD").stdout.strip()
    remove_exec_worktree(
        session_folder,
        exec_id=exec_id,
        git_root=ew.git_root,
        branch=ew.branch,
        worktree_path=ew.worktree_path,
    )
    return MergeResult(status="merged", commit_sha=sha, conflict_files=[])


def _list_conflicts(git_root: Path) -> list[str]:
    r = _run_git(git_root, "diff", "--name-only", "--diff-filter=U", check=False)
    return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
