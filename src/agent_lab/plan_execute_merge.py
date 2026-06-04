"""In-product merge for worktree executions (M0 spike)."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
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
    ``oracle_call`` lets tests or future wiring route to a real oracle. Live
    Claude invocation is opt-in via ``AGENT_LAB_ORACLE_LIVE=1``.
    """
    verify = _action_verify(action)
    if _missing_verify(verify):
        return {
            "verdict": "skipped",
            "detail": "verify field missing",
            "verify_criterion": verify,
            "checked_paths": [],
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
    prompt = _oracle_prompt(verify, snippets)

    if oracle_call is not None:
        raw = oracle_call(prompt)
    elif os.getenv("AGENT_LAB_ORACLE_LIVE", "").strip().lower() in {"1", "true", "yes"}:
        from agent_lab import claude_cli

        raw = claude_cli.invoke("oracle", prompt, scribe=True)
    else:
        raw = _mock_oracle_response(verify, snippets)

    detail = str(raw or "").strip()
    verdict = "pass" if detail.upper().startswith("PASS") else "fail"
    return {
        "verdict": verdict,
        "detail": detail[:400],
        "verify_criterion": verify,
        "checked_paths": checked_paths,
    }


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


def _oracle_prompt(verify: str, snippets: list[str]) -> str:
    files_block = "\n\n".join(snippets) or "(changed files unavailable)"
    return (
        "Independently verify whether this plan action is complete.\n\n"
        f"Verification criterion:\n{verify}\n\n"
        f"Merged file snippets:\n{files_block}\n\n"
        "Respond with exactly one leading verdict: PASS or FAIL. "
        "If FAIL, give the concrete reason in 1-2 lines."
    )


def _mock_oracle_response(verify: str, snippets: list[str]) -> str:
    if not snippets:
        return "FAIL: no readable merged files to check"
    body = "\n\n".join(snippets)
    literals = _verify_literals(verify)
    missing = [literal for literal in literals if literal not in body]
    if missing:
        return f"FAIL: missing expected literal(s): {', '.join(missing[:5])}"
    if literals:
        return f"PASS: found expected literal(s): {', '.join(literals[:5])}"
    return "PASS: mock oracle checked merged files; no explicit literal criterion found"


def _verify_literals(verify: str) -> list[str]:
    import re

    literals: list[str] = []
    for token in re.findall(r"`([^`]+)`", verify or ""):
        text = token.strip()
        if not text:
            continue
        if "/" in text or "\\" in text or Path(text).suffix:
            continue
        if text not in literals:
            literals.append(text)
    return literals


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
    merge = execution.get("merge") if isinstance(execution.get("merge"), dict) else {}
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
