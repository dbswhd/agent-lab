"""Isolation policy for plan execute actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agent_lab.plan_actions import PlanAction, action_key
from agent_lab.plan_execute_git import (
    default_branch,
    detect_git_root,
    git_roots_for_paths,
    paths_under_git_root,
)

IsolationKind = Literal["worktree", "apply", "block", "snapshot_override"]
IsolationSource = Literal["auto", "plan", "override"]


@dataclass(frozen=True)
class IsolationDecision:
    action_key: str
    isolation: IsolationKind
    isolation_source: IsolationSource
    monitored_paths: list[str]
    git_root: Path | None = None
    git_root_detected: bool = False
    paths_under_root: bool = True
    base_branch: str = "main"
    block_reason: str | None = None
    override: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_key": self.action_key,
            "isolation": self.isolation,
            "isolation_source": self.isolation_source,
            "monitored_paths": self.monitored_paths,
            "git_root": str(self.git_root) if self.git_root else None,
            "git_root_detected": self.git_root_detected,
            "paths_under_root": self.paths_under_root,
            "base_branch": self.base_branch,
            "block_reason": self.block_reason,
            "override": self.override,
        }


def resolve_action_isolation(
    action: PlanAction,
    permissions: dict[str, Any] | None = None,
    cwd_hint: Path | None = None,
    *,
    override: dict[str, Any] | None = None,
) -> IsolationDecision:
    """Resolve per-action isolation. Cleanliness is enforced by worktree creation."""
    del permissions  # reserved for future workspace-binding policy
    monitored = action.monitored_paths()
    key = action_key(action.kind, action.index)

    if override and override.get("mode") == "snapshot_override":
        return IsolationDecision(
            action_key=key,
            isolation="snapshot_override",
            isolation_source="override",
            monitored_paths=monitored,
            override=dict(override),
        )

    requested = (action.isolation or "auto").strip().lower()
    source: IsolationSource = "auto" if requested == "auto" else "plan"
    roots = git_roots_for_paths(monitored, cwd_hint=cwd_hint)
    if not roots and cwd_hint is not None:
        hinted_root = detect_git_root(cwd_hint)
        if hinted_root is not None:
            roots = {hinted_root.resolve()}
    root = next(iter(roots)) if len(roots) == 1 else None
    under = bool(root and (not monitored or paths_under_git_root(root, monitored, cwd_hint=cwd_hint)))

    if requested == "block":
        return IsolationDecision(
            action_key=key,
            isolation="block",
            isolation_source=source,
            monitored_paths=monitored,
            git_root=root,
            git_root_detected=root is not None,
            paths_under_root=under,
            base_branch=default_branch(root) if root else "main",
            block_reason="isolation=block",
        )

    if len(roots) > 1:
        return IsolationDecision(
            action_key=key,
            isolation="block",
            isolation_source=source,
            monitored_paths=monitored,
            paths_under_root=False,
            block_reason="paths_span_repos",
        )

    if requested == "apply":
        return IsolationDecision(
            action_key=key,
            isolation="apply",
            isolation_source=source,
            monitored_paths=monitored,
            git_root=root,
            git_root_detected=root is not None,
            paths_under_root=under if root else True,
            base_branch=default_branch(root) if root else "main",
        )

    if requested == "worktree" and root is None:
        return IsolationDecision(
            action_key=key,
            isolation="block",
            isolation_source=source,
            monitored_paths=monitored,
            git_root_detected=False,
            paths_under_root=True,
            block_reason="git_root_missing",
        )

    if root is None:
        return IsolationDecision(
            action_key=key,
            isolation="apply",
            isolation_source=source,
            monitored_paths=monitored,
            git_root_detected=False,
            paths_under_root=True,
        )

    return IsolationDecision(
        action_key=key,
        isolation="worktree",
        isolation_source=source,
        monitored_paths=monitored,
        git_root=root,
        git_root_detected=True,
        paths_under_root=under,
        base_branch=default_branch(root),
    )
