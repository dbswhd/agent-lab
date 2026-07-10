"""Git worktree lifecycle for isolated plan execute (M0 spike)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.plan.execute_git import (
    _run_git,
    default_branch,
    exec_branch_name,
    is_working_tree_clean,
)

log = logging.getLogger(__name__)


def _rmtree_best_effort(path: Path) -> None:
    """Remove a worktree directory; log (don't raise) on failure.

    Callers treat worktree cleanup as fail-open so a stuck directory never
    blocks a room turn or execute action, but a silent ``ignore_errors=True``
    lets orphaned worktrees accumulate with no way to notice. Logging keeps
    the fail-open behavior while making repeated failures observable.
    """
    try:
        shutil.rmtree(path)
    except OSError:
        log.warning("failed to remove worktree directory %s", path, exc_info=True)


class WorktreeUnavailable(Exception):
    """Cannot create isolated worktree."""

    def __init__(
        self,
        message: str,
        *,
        reason: str = "worktree_unavailable",
        execution_id: str | None = None,
    ):
        super().__init__(message)
        self.reason = reason
        self.execution_id = execution_id


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
        _rmtree_best_effort(wt_path)

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
        try:
            from agent_lab.worktree_hooks import run_worktree_remove

            # Best-effort: remove hooks must not block teardown.
            run_worktree_remove(worktree_path=wt, git_root=root)
        except Exception:
            log.warning("worktree remove hooks failed for %s", wt, exc_info=True)
        _run_git(root, "worktree", "remove", "--force", str(wt.resolve()), check=False)
        if wt.exists():
            _rmtree_best_effort(wt)
    _run_git(root, "worktree", "prune", check=False)
    _run_git(root, "branch", "-D", branch, check=False)


def discard_exec_worktree(ew: ExecWorktree, session_folder: Path, exec_id: str) -> None:
    """Reject path: drop worktree without merging."""
    if ew.worktree_path.exists() or ew.branch:
        remove_exec_worktree(
            session_folder,
            exec_id=exec_id,
            git_root=ew.git_root,
            branch=ew.branch,
            worktree_path=ew.worktree_path,
        )
        return
    fallback = worktree_dir(session_folder, exec_id)
    if fallback.exists():
        _remove_unknown_worktree(fallback, prune_roots={ew.git_root.resolve()})


def _execution_worktree(row: dict[str, Any]) -> ExecWorktree | None:
    required = ("git_root", "worktree_path", "exec_branch", "base_branch", "base_sha")
    if not all(row.get(key) for key in required):
        return None
    return ExecWorktree(
        git_root=Path(str(row["git_root"])),
        worktree_path=Path(str(row["worktree_path"])),
        branch=str(row["exec_branch"]),
        base_branch=str(row["base_branch"]),
        base_sha=str(row["base_sha"]),
    )


def _git_root_from_worktree_path(path: Path) -> Path | None:
    if not path.is_dir():
        return None
    try:
        common = _run_git(path, "rev-parse", "--git-common-dir").stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    if not common:
        return None
    p = Path(common)
    if not p.is_absolute():
        p = (path / p).resolve()
    if p.name == ".git":
        return p.parent.resolve()
    return None


def _remove_unknown_worktree(path: Path, *, prune_roots: set[Path]) -> None:
    root = _git_root_from_worktree_path(path)
    if root is not None:
        prune_roots.add(root)
        _run_git(root, "worktree", "remove", "--force", str(path.resolve()), check=False)
    if path.exists():
        _rmtree_best_effort(path)


def list_orphan_worktrees(
    session_folder: Path,
    run_meta: RunStateLike,
) -> list[Path]:
    """Return session worktree dirs no longer referenced by run.json executions."""
    root = session_folder / "worktrees"
    if not root.is_dir():
        return []
    known = {str(row.get("id")) for row in run_meta.get("executions") or [] if isinstance(row, dict) and row.get("id")}
    return sorted(path for path in root.iterdir() if path.is_dir() and path.name not in known)


def gc_stale_worktrees(session_folder: Path, run_meta: RunStateLike) -> list[str]:
    """Remove terminal and orphan session worktrees; keep pending approval worktrees."""
    removed: list[str] = []
    prune_roots: set[Path] = set()
    terminal = {"merged", "rejected"}

    for row in run_meta.get("executions") or []:
        if not isinstance(row, dict):
            continue
        if row.get("status") not in terminal:
            continue
        exec_id = str(row.get("id") or "")
        if not exec_id:
            continue
        wt = Path(str(row.get("worktree_path") or worktree_dir(session_folder, exec_id)))
        if not wt.exists():
            continue
        ew = _execution_worktree(row)
        if ew is not None:
            remove_exec_worktree(
                session_folder,
                exec_id=exec_id,
                git_root=ew.git_root,
                branch=ew.branch,
                worktree_path=wt,
            )
            prune_roots.add(ew.git_root.resolve())
        else:
            _remove_unknown_worktree(wt, prune_roots=prune_roots)
        removed.append(str(wt))

    for wt in list_orphan_worktrees(session_folder, run_meta):
        _remove_unknown_worktree(wt, prune_roots=prune_roots)
        removed.append(str(wt))

    for root in prune_roots:
        _run_git(root, "worktree", "prune", check=False)

    worktrees_root = session_folder / "worktrees"
    if worktrees_root.is_dir() and not any(worktrees_root.iterdir()):
        worktrees_root.rmdir()
    return removed
