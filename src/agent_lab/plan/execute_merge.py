"""In-product merge for worktree executions (M0 spike)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agent_lab.time_utils import utc_now_iso as _utc_now
from agent_lab.env_flags import env_bool
from agent_lab.plan.execute_git import _run_git, is_working_tree_clean
from agent_lab.plan.execute_worktree import ExecWorktree, remove_exec_worktree


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


def oracle_verify(
    action: Any,
    merged_paths: list[str | Path],
    *,
    session_folder: Path | None = None,
    workspace_root: Path | None = None,
    oracle_call: Callable[[str], str] | None = None,
    max_paths: int = 5,
    max_chars_per_file: int = 600,
) -> dict[str, Any]:
    """Mock-first independent verifier for merged plan actions.

    By default this is deterministic and offline: it checks backtick literals in
    ``action.verify`` against snippets from ``merged_paths``. Supplying
    ``oracle_call`` lets tests route to a real oracle. Live Claude invocation is
    opt-in via ``AGENT_LAB_ORACLE_LIVE=1`` (see ``oracle_core``).
    """
    from agent_lab.oracle_core import (
        build_execute_oracle_prompt,
        build_oracle_result,
        invoke_oracle,
        mock_execute_oracle_response,
        resolved_oracle_model,
        session_oracle_context,
    )

    verify = _action_verify(action)
    if _missing_verify(verify):
        return {
            "verdict": "skipped",
            "detail": "verify field missing",
            "verify_criterion": verify,
            "checked_paths": [],
            "evidence": [],
            "source": "mock",
        }

    base = _oracle_workspace_root(
        session_folder=session_folder,
        workspace_root=workspace_root,
    )
    snippets, checked_paths = _oracle_file_snippets(
        merged_paths,
        workspace_root=base,
        max_paths=max_paths,
        max_chars_per_file=max_chars_per_file,
    )
    prompt = build_execute_oracle_prompt(
        verify,
        snippets,
        extra_evidence=session_oracle_context(session_folder),
    )

    if oracle_call is not None:
        raw, source = invoke_oracle("execute", prompt, oracle_call=oracle_call)
    elif env_bool("AGENT_LAB_ORACLE_LIVE"):
        raw, source = invoke_oracle("execute", prompt, session_folder=session_folder)
    else:
        raw = mock_execute_oracle_response(verify, snippets)
        source = "mock"

    return build_oracle_result(
        raw=raw,
        source=source,
        kind="execute",
        verify_criterion=verify,
        checked_paths=checked_paths,
        model=resolved_oracle_model("execute") if source == "live" else None,
    )


def verify_after_merge(
    action: Any,
    merged_paths: list[str | Path],
    *,
    session_folder: Path | None = None,
    workspace_root: Path | None = None,
    verify_retries: int = 0,
    oracle_call: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Mock Layer-3 post-merge verifier that delegates to ``oracle_verify``."""
    oracle = oracle_verify(
        action,
        merged_paths,
        session_folder=session_folder,
        workspace_root=workspace_root,
        oracle_call=oracle_call,
    )
    status = "passed" if oracle.get("verdict") == "pass" else "failed"
    if oracle.get("verdict") == "skipped":
        status = "skipped"
    return {
        "status": status,
        "verify_retries": verify_retries,
        "oracle": oracle,
    }


def _action_verify(action: Any) -> str:
    if isinstance(action, dict):
        return str(action.get("verify") or action.get("action_verify") or "")
    return str(getattr(action, "verify", "") or "")


def _missing_verify(verify: str) -> bool:
    text = (verify or "").strip()
    return text in {"", "검증 기준 없음", "-", "—", "N/A", "n/a", "none", "None"}


def _oracle_workspace_root(
    *,
    session_folder: Path | None,
    workspace_root: Path | None,
) -> Path:
    if workspace_root is not None:
        return workspace_root.expanduser().resolve()
    if session_folder is not None:
        return session_folder.expanduser().resolve().parent
    return Path.cwd().resolve()


def _oracle_file_snippets(
    paths: list[str | Path],
    *,
    workspace_root: Path,
    max_paths: int,
    max_chars_per_file: int,
) -> tuple[list[str], list[str]]:
    snippets: list[str] = []
    checked: list[str] = []
    for raw in paths[: max(max_paths, 0)]:
        display = str(raw)
        path = Path(raw).expanduser()
        full = path if path.is_absolute() else workspace_root / path
        if not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        checked.append(display)
        snippets.append(f"--- {display} ---\n{text[:max_chars_per_file]}")
    return snippets, checked


def archive_executed_diff(
    session_folder: Path,
    *,
    execution_id: str,
    execution: dict[str, Any],
) -> Path | None:
    """Persist merged execution diff under ``sessions/<id>/executed/`` (PI-executed)."""
    diff = str(execution.get("diff") or "").strip()
    if not diff:
        return None
    out_dir = session_folder / "executed"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{execution_id}.json"
    if dest.is_file():
        return dest
    merge_raw = execution.get("merge")
    merge: dict[str, Any] = merge_raw if isinstance(merge_raw, dict) else {}
    payload = {
        "execution_id": execution_id,
        "action_id": execution.get("action_id"),
        "action_index": execution.get("action_index"),
        "commit_sha": merge.get("commit_sha"),
        "merged_at": merge.get("completed_at") or _utc_now(),
        "diff_stat": execution.get("diff_stat"),
        "diff": diff[:500_000],
    }
    dest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dest


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


def abort_exec_merge(
    ew: ExecWorktree,
    *,
    session_folder: Path,
    exec_id: str,
) -> MergeResult:
    """Abort an in-progress merge and discard the exec worktree."""
    root = ew.git_root.resolve()
    _run_git(root, "merge", "--abort", check=False)
    remove_exec_worktree(
        session_folder,
        exec_id=exec_id,
        git_root=ew.git_root,
        branch=ew.branch,
        worktree_path=ew.worktree_path,
    )
    return MergeResult(status="conflict", commit_sha=None, conflict_files=[])


def confirm_exec_merge(
    ew: ExecWorktree,
    *,
    session_folder: Path,
    exec_id: str,
) -> MergeResult:
    """Confirm Human-resolved merge; base must be clean and no conflicts remain."""
    root = ew.git_root.resolve()
    conflicts = _list_conflicts(root)
    if conflicts:
        raise ValueError(f"merge conflicts remain: {', '.join(conflicts)}")
    diff_check = _run_git(root, "diff", "--check", check=False)
    if diff_check.returncode != 0:
        detail = (diff_check.stdout or diff_check.stderr or "git diff --check failed").strip()
        raise ValueError(detail)
    if not is_working_tree_clean(root):
        raise ValueError("base branch must be clean after conflict resolution commit")
    sha = _run_git(root, "rev-parse", "HEAD").stdout.strip()
    remove_exec_worktree(
        session_folder,
        exec_id=exec_id,
        git_root=ew.git_root,
        branch=ew.branch,
        worktree_path=ew.worktree_path,
    )
    return MergeResult(status="merged", commit_sha=sha, conflict_files=[])
