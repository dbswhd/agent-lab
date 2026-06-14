"""Work tab stepper phase — Python SSOT (mirrors web WorkStatusBar)."""

from __future__ import annotations

from typing import Any, Literal

WorkPhase = Literal[
    "plan_draft",
    "review_needed",
    "execute_pending",
    "merge_verify",
    "done",
]

WORK_PHASES: frozenset[str] = frozenset(
    {
        "plan_draft",
        "review_needed",
        "execute_pending",
        "merge_verify",
        "done",
    }
)


def resolve_work_phase_from_mission(
    mission_phase: str | None,
    *,
    resume_phase: str | None = None,
) -> WorkPhase | None:
    if not (mission_phase or "").strip():
        return None
    phase = mission_phase.strip().upper()
    if phase == "MISSION_PAUSED":
        resume = (resume_phase or "").strip()
        if resume:
            return resolve_work_phase_from_mission(resume, resume_phase=None)
        return "plan_draft"
    if phase == "MISSION_DONE":
        return "done"
    if phase in {"MERGE_REVIEW", "PLAN_REJECT"}:
        return "review_needed"
    if phase == "VERIFY":
        return "merge_verify"
    if phase in {"EXECUTE_QUEUE", "DRY_RUN", "REPAIR"}:
        return "execute_pending"
    if phase in {"DISCUSS", "PLAN_GATE", "MISSION_DEFINE"}:
        return "plan_draft"
    return None


def resolve_work_phase_standalone(
    *,
    has_plan: bool,
    has_pending_execution: bool,
    has_dry_run_diff: bool,
    pending_agreement: bool,
    latest_execution: dict[str, Any] | None,
) -> WorkPhase:
    exec_row = latest_execution or {}
    status = str(exec_row.get("status") or "")
    oracle = exec_row.get("oracle") if isinstance(exec_row.get("oracle"), dict) else {}
    oracle_pass = str(oracle.get("verdict") or "").strip().lower() == "pass"
    if status == "completed" and oracle_pass:
        return "done"
    if exec_row and (
        status in {"merged", "review_required", "pending_approval", "merge_conflict", "pending"}
        or oracle
    ):
        return "merge_verify"
    if has_pending_execution:
        return "execute_pending"
    if has_dry_run_diff or pending_agreement:
        return "review_needed"
    if has_plan:
        return "plan_draft"
    return "plan_draft"


def resolve_work_phase(
    *,
    mission_enabled: bool,
    mission_phase: str | None,
    resume_phase: str | None,
    plan_workflow_phase: str | None = None,
    plan_workflow_enabled: bool = False,
    has_plan: bool,
    has_pending_execution: bool,
    has_dry_run_diff: bool,
    pending_agreement: bool,
    latest_execution: dict[str, Any] | None,
) -> WorkPhase:
    if plan_workflow_enabled:
        from agent_lab.plan_workflow import resolve_work_phase_from_plan_workflow

        from_plan = resolve_work_phase_from_plan_workflow(plan_workflow_phase)
        if from_plan is not None and from_plan != "execute_pending":
            return from_plan  # type: ignore[return-value]
    if mission_enabled:
        from_mission = resolve_work_phase_from_mission(
            mission_phase,
            resume_phase=resume_phase,
        )
        if from_mission is not None:
            return from_mission
    if plan_workflow_enabled:
        from agent_lab.plan_workflow import resolve_work_phase_from_plan_workflow

        from_plan = resolve_work_phase_from_plan_workflow(plan_workflow_phase)
        if from_plan == "execute_pending":
            return from_plan  # type: ignore[return-value]
    return resolve_work_phase_standalone(
        has_plan=has_plan,
        has_pending_execution=has_pending_execution,
        has_dry_run_diff=has_dry_run_diff,
        pending_agreement=pending_agreement,
        latest_execution=latest_execution,
    )
