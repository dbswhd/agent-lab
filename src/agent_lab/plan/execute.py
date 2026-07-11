from __future__ import annotations

"""Thin execute facade — plan action → dry-run → Human approve (F9)."""

from pathlib import Path
from typing import Any

from agent_lab.core.execution_status_scopes import PENDING_STATUS
from agent_lab.plan.actions import parse_plan_action_sections
from agent_lab.plan.execute_dry_run import run_dry_run
from agent_lab.plan.execute_merge import verify_after_merge
from agent_lab.plan.execute_prompts import _call_execute_agent
from agent_lab.plan.execute_resolve import (
    abort_merge_execution,
    cancel_open_execution,
    confirm_merge_execution,
    resolve_execution,
    revise_pending_execution,
    reverify_merged_execution,
    run_isolation_override,
)
from agent_lab.plan.execute_shared import (
    MAX_DIFF_CHARS,
    MAX_VERIFY_RETRIES,
    _exec_worktree_from_execution,
    _now,
    _rewrite_git_paths_in_text,
)
from agent_lab.plan.execute_status import execution_allows_task_complete
from agent_lab.runtime.adapters import execute_agent_available as _execute_agent_available
from agent_lab.workspace.roots import (
    execute_workspace_info,
    resolve_execute_workspace,
    workspace_path_info,
)


def list_plan_actions(
    folder: Path,
    *,
    permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan_path = folder / "plan.md"
    if not plan_path.is_file():
        return {
            "recommended": None,
            "now": [],
            "roadmap": [],
            "actions": [],
        }
    plan_md = plan_path.read_text(encoding="utf-8")
    sections = parse_plan_action_sections(plan_md)
    recommended = sections["recommended"]
    if recommended is not None:
        monitored = recommended.get("monitored_paths") or recommended.get("expected_paths") or []
        recommended = dict(recommended)
        recommended["execute_workspace"] = execute_workspace_info(permissions, monitored)
    return {
        "recommended": recommended,
        "now": sections.get("now") or [],
        "roadmap": sections["roadmap"],
        "actions": sections["actions"],
    }


__all__ = [
    "MAX_DIFF_CHARS",
    "MAX_VERIFY_RETRIES",
    "PENDING_STATUS",
    "_call_execute_agent",
    "_exec_worktree_from_execution",
    "_execute_agent_available",
    "_now",
    "_rewrite_git_paths_in_text",
    "abort_merge_execution",
    "cancel_open_execution",
    "confirm_merge_execution",
    "execution_allows_task_complete",
    "list_plan_actions",
    "resolve_execute_workspace",
    "resolve_execution",
    "reverify_merged_execution",
    "revise_pending_execution",
    "run_dry_run",
    "run_isolation_override",
    "verify_after_merge",
    "workspace_path_info",
]
