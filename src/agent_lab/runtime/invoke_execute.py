"""Mission → execute invocations (reverse edge of the orchestration triangle)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def run_dry_run(
    folder: Path,
    *,
    action_index: int,
    permissions: dict[str, Any] | None = None,
    executor: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from agent_lab.plan_execute import run_dry_run as _run_dry_run

    return _run_dry_run(
        folder,
        action_index=action_index,
        permissions=permissions,
        executor=executor,
        **kwargs,
    )


def reverify_merged_execution(
    folder: Path,
    *,
    execution_id: str,
    permissions: dict[str, Any] | None = None,
    executor: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from agent_lab.plan_execute import reverify_merged_execution as _reverify

    return _reverify(
        folder,
        execution_id=execution_id,
        permissions=permissions,
        executor=executor,
        **kwargs,
    )


def cancel_open_execution(
    folder: Path,
    *,
    execution_id: str | None = None,
    reason: str = "user_cancel",
) -> dict[str, Any]:
    from agent_lab.plan_execute import cancel_open_execution as _cancel

    return _cancel(folder, execution_id=execution_id, reason=reason)


def list_plan_actions(
    folder: Path,
    *,
    permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from agent_lab.plan_execute import list_plan_actions as _list

    return _list(folder, permissions=permissions)


def execution_allows_task_complete(execution: dict[str, Any]) -> bool:
    from agent_lab.plan_execute import execution_allows_task_complete as _allows

    return _allows(execution)
