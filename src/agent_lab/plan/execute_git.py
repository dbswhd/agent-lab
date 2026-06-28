"""Git root detection and per-action execute context (M0 worktree spike)."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

IsolationKind = Literal["worktree", "apply", "block"]

_BRANCH_SAFE = re.compile(r"[^a-zA-Z0-9._/-]+")


@dataclass(frozen=True)
class ActionGitContext:
    action_key: str
    git_root: Path | None
    git_root_detected: bool
    isolation: IsolationKind
    isolation_source: str
    monitored_paths: list[str]
    paths_under_root: bool
    base_branch: str
    block_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_key": self.action_key,
            "git_root": str(self.git_root) if self.git_root else None,
            "git_root_detected": self.git_root_detected,
            "isolation": self.isolation,
            "isolation_source": self.isolation_source,
            "monitored_paths": self.monitored_paths,
            "paths_under_root": self.paths_under_root,
            "base_branch": self.base_branch,
            "block_reason": self.block_reason,
        }


def _run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def detect_git_root(start: Path) -> Path | None:
    """Return git toplevel for path, or None."""
    path = start.expanduser().resolve()
    if path.is_file():
        path = path.parent
    if not path.is_dir():
        return None
    try:
        r = _run_git(path, "rev-parse", "--show-toplevel")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    top = Path(r.stdout.strip())
    return top if top.is_dir() else None


def default_branch(git_root: Path) -> str:
    try:
        r = _run_git(git_root, "symbolic-ref", "--short", "HEAD")
        name = r.stdout.strip()
        if name:
            return name
    except subprocess.CalledProcessError:
        pass
    for candidate in ("main", "master"):
        try:
            _run_git(git_root, "rev-parse", "--verify", candidate)
            return candidate
        except subprocess.CalledProcessError:
            continue
    return "main"


def git_roots_for_paths(paths: list[str], *, cwd_hint: Path | None = None) -> set[Path]:
    """Distinct git roots for paths (empty if none in a repo)."""
    roots: set[Path] = set()
    for raw in paths:
        raw = (raw or "").strip()
        if not raw:
            continue
        p = Path(raw).expanduser()
        if not p.is_absolute() and cwd_hint is not None:
            p = (cwd_hint / p).resolve()
        else:
            p = p.resolve()
        if p.is_file():
            p = p.parent
        root = detect_git_root(p)
        if root is not None:
            roots.add(root.resolve())
    return roots


def git_root_for_paths(paths: list[str], *, cwd_hint: Path | None = None) -> Path | None:
    """Single common git root, or None if ambiguous or not in git."""
    roots = git_roots_for_paths(paths, cwd_hint=cwd_hint)
    if len(roots) > 1:
        return None
    if len(roots) == 1:
        return next(iter(roots))
    if cwd_hint is not None:
        return detect_git_root(cwd_hint)
    return None


def paths_under_git_root(git_root: Path, paths: list[str], *, cwd_hint: Path | None) -> bool:
    root = git_root.resolve()
    for raw in paths:
        raw = (raw or "").strip()
        if not raw:
            continue
        p = Path(raw).expanduser()
        if not p.is_absolute() and cwd_hint is not None:
            p = (cwd_hint / p).resolve()
        else:
            p = p.resolve()
        try:
            if p.is_file():
                p.relative_to(root)
            else:
                (cwd_hint / raw if cwd_hint and not Path(raw).is_absolute() else p).resolve().relative_to(root)
        except ValueError:
            return False
    return True


def sanitize_branch_name(name: str, *, max_len: int = 80) -> str:
    s = _BRANCH_SAFE.sub("-", name.strip()).strip("-")
    s = s.replace("/", "-")
    while "--" in s:
        s = s.replace("--", "-")
    if not s:
        s = "agent-lab-exec"
    return s[:max_len]


def exec_branch_name(
    session_id: str,
    action_key: str,
    exec_id: str,
) -> str:
    short = exec_id.replace("exec-", "")[:10]
    slug = sanitize_branch_name(session_id)[-32:]
    ak = sanitize_branch_name(action_key.replace(":", "-"))
    return f"agent-lab/{slug}-{ak}-{short}"


def resolve_action_git_context(
    *,
    action_key: str,
    monitored_paths: list[str],
    cwd_hint: Path | None = None,
    isolation_requested: str = "auto",
) -> ActionGitContext:
    req = (isolation_requested or "auto").strip().lower()
    roots_set = git_roots_for_paths(monitored_paths, cwd_hint=cwd_hint)
    roots_for_paths = next(iter(roots_set)) if len(roots_set) == 1 else None
    if len(roots_set) > 1:
        roots_for_paths = None
    under = bool(
        roots_for_paths
        and (not monitored_paths or paths_under_git_root(roots_for_paths, monitored_paths, cwd_hint=cwd_hint))
    )

    if req == "block":
        return ActionGitContext(
            action_key=action_key,
            git_root=roots_for_paths,
            git_root_detected=roots_for_paths is not None,
            isolation="block",
            isolation_source="explicit",
            monitored_paths=monitored_paths,
            paths_under_root=under,
            base_branch=default_branch(roots_for_paths) if roots_for_paths else "main",
            block_reason="isolation=block",
        )

    if req == "apply":
        return ActionGitContext(
            action_key=action_key,
            git_root=roots_for_paths,
            git_root_detected=roots_for_paths is not None,
            isolation="apply",
            isolation_source="explicit",
            monitored_paths=monitored_paths,
            paths_under_root=under,
            base_branch=default_branch(roots_for_paths) if roots_for_paths else "main",
        )

    if len(roots_set) > 1:
        return ActionGitContext(
            action_key=action_key,
            git_root=None,
            git_root_detected=False,
            isolation="block",
            isolation_source="auto",
            monitored_paths=monitored_paths,
            paths_under_root=False,
            base_branch="main",
            block_reason="paths_span_repos",
        )

    if roots_for_paths is None and monitored_paths:
        return ActionGitContext(
            action_key=action_key,
            git_root=None,
            git_root_detected=False,
            isolation="apply",
            isolation_source="auto",
            monitored_paths=monitored_paths,
            paths_under_root=True,
            base_branch="main",
        )

    if roots_for_paths is None:
        return ActionGitContext(
            action_key=action_key,
            git_root=None,
            git_root_detected=False,
            isolation="apply",
            isolation_source="auto",
            monitored_paths=monitored_paths,
            paths_under_root=True,
            base_branch="main",
        )

    return ActionGitContext(
        action_key=action_key,
        git_root=roots_for_paths,
        git_root_detected=True,
        isolation="worktree",
        isolation_source="auto" if req == "auto" else req,
        monitored_paths=monitored_paths,
        paths_under_root=under,
        base_branch=default_branch(roots_for_paths),
    )


def is_working_tree_clean(git_root: Path) -> bool:
    r = _run_git(git_root, "status", "--porcelain")
    return not (r.stdout or "").strip()
