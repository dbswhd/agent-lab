"""Plan workflow, execute gate, and action parsing.

Public facade — submodules under ``agent_lab.plan.*``.
Lazy re-exports keep ``from agent_lab.plan import get_plan_workflow`` stable.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "PlanAction",
    "PlanActionKind",
    "PlanSnapshotRequired",
    "PlanWorkflowNotApproved",
    "actions",
    "advance",
    "approve_plan",
    "ensure_plan_snapshot_approved",
    "ensure_plan_workflow_approved",
    "execute",
    "get_plan_workflow",
    "is_plan_workflow_active",
    "list_plan_actions",
    "parse_plan_actions",
    "paths",
    "pending",
    "plan_workflow_phase",
    "provenance",
    "refs",
    "reject_plan",
    "resolve_execution",
    "run_dry_run",
    "workflow",
]

_SUBMODULES = frozenset(
    {
        "actions",
        "advance",
        "execute",
        "paths",
        "pending",
        "provenance",
        "refs",
        "workflow",
    }
)

_EXPORTS: dict[str, tuple[str, str]] = {
    "PlanAction": ("agent_lab.plan.actions", "PlanAction"),
    "PlanActionKind": ("agent_lab.plan.actions", "PlanActionKind"),
    "parse_plan_actions": ("agent_lab.plan.actions", "parse_plan_actions"),
    "PlanSnapshotRequired": ("agent_lab.plan.pending", "PlanSnapshotRequired"),
    "ensure_plan_snapshot_approved": (
        "agent_lab.plan.pending",
        "ensure_plan_snapshot_approved",
    ),
    "PlanWorkflowNotApproved": ("agent_lab.plan.workflow", "PlanWorkflowNotApproved"),
    "approve_plan": ("agent_lab.plan.workflow", "approve_plan"),
    "ensure_plan_workflow_approved": (
        "agent_lab.plan.workflow",
        "ensure_plan_workflow_approved",
    ),
    "get_plan_workflow": ("agent_lab.plan.workflow", "get_plan_workflow"),
    "is_plan_workflow_active": ("agent_lab.plan.workflow", "is_plan_workflow_active"),
    "plan_workflow_phase": ("agent_lab.plan.workflow", "plan_workflow_phase"),
    "reject_plan": ("agent_lab.plan.workflow", "reject_plan"),
    "list_plan_actions": ("agent_lab.plan.execute", "list_plan_actions"),
    "resolve_execution": ("agent_lab.plan.execute", "resolve_execution"),
    "run_dry_run": ("agent_lab.plan.execute", "run_dry_run"),
}


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        return importlib.import_module(f"{__name__}.{name}")
    spec = _EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod_name, attr = spec
    return getattr(importlib.import_module(mod_name), attr)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
