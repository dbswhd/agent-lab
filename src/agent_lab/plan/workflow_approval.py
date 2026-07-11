from __future__ import annotations

"""Plan workflow Human approval gate."""

import uuid
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunState

from agent_lab.plan.pending import plan_content_hash
from agent_lab.plan.workflow_state import (
    PlanWorkflowNotApproved,
    PlanWorkflowPhase,
    apply_plan_substate_patch,
    derive_loop_goal_from_plan,
    get_plan_workflow,
    is_plan_workflow_active,
)
from agent_lab.time_utils import utc_now_iso as _now
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.turn_modes import approval_starts_execute_loop
from agent_lab.verified_loop import DEFAULT_COMPLETION_PROMISE


def ensure_plan_workflow_approved(folder: Path) -> None:
    run = read_run_meta(folder)
    if not is_plan_workflow_active(run):
        return
    workflow = get_plan_workflow(run)
    phase = str(workflow.get("phase") or "INTAKE")
    if phase != "APPROVED":
        raise PlanWorkflowNotApproved(phase)
    plan_path = folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    approved_hash = str(workflow.get("plan_hash_at_approval") or "")
    if approved_hash and approved_hash == plan_content_hash(plan_md):
        return

    def _invalidate(current: dict[str, Any]) -> dict[str, Any]:
        return apply_plan_substate_patch(
            current,
            phase="HUMAN_PENDING",
            notice="plan_changed_after_approval",
        )

    patch_run_meta(folder, _invalidate)
    raise PlanWorkflowNotApproved(phase, "plan_workflow_plan_changed")


def approve_plan(
    session_folder: Path,
    *,
    goal: str | None = None,
    completion_promise: str | None = None,
    criteria: str | None = None,
    plan_md: str | None = None,
) -> dict[str, Any]:
    run = read_run_meta(session_folder)
    pw = get_plan_workflow(run)
    if not pw.get("enabled"):
        raise ValueError("plan workflow is not enabled")
    if str(pw.get("phase") or "") != "HUMAN_PENDING":
        raise ValueError("plan is not awaiting Human approval")
    return _finalize_plan_approval(
        session_folder,
        goal=goal,
        completion_promise=completion_promise,
        criteria=criteria,
        plan_md=plan_md,
        approved_by="human",
    )


def approve_plan_bypass(
    session_folder: Path,
    *,
    goal: str | None = None,
    completion_promise: str | None = None,
    criteria: str | None = None,
    plan_md: str | None = None,
    approved_by: str = "template",
) -> dict[str, Any]:
    """Template fast-path — skip HUMAN_PENDING; reuse approve side effects."""
    return _finalize_plan_approval(
        session_folder,
        goal=goal,
        completion_promise=completion_promise,
        criteria=criteria,
        plan_md=plan_md,
        approved_by=approved_by,
        enable_workflow=True,
    )


def _finalize_plan_approval(
    session_folder: Path,
    *,
    goal: str | None = None,
    completion_promise: str | None = None,
    criteria: str | None = None,
    plan_md: str | None = None,
    approved_by: str = "human",
    enable_workflow: bool = False,
) -> dict[str, Any]:
    path = session_folder / "plan.md"
    md = plan_md if plan_md is not None else (path.read_text(encoding="utf-8") if path.is_file() else "")
    if not (md or "").strip():
        raise ValueError("plan.md is empty")

    derived = derive_loop_goal_from_plan(md)
    goal_text = (goal or derived["goal"]).strip()
    criteria_resolved = (criteria or derived["criteria"]).strip() or goal_text
    promise = (completion_promise or derived["completion_promise"]).strip() or DEFAULT_COMPLETION_PROMISE
    if not goal_text:
        raise ValueError("plan goal text is required")

    plan_hash = plan_content_hash(md)
    now = _now()
    approved = {
        "text": goal_text,
        "completion_promise": promise,
        "criteria": criteria_resolved,
        "approved_at": now,
        "approved_by": approved_by,
    }
    oracle_session_id = f"oracle_{session_folder.name}_{uuid.uuid4().hex[:8]}"
    run_before = read_run_meta(session_folder)
    start_execute_loop = approval_starts_execute_loop(run_before)

    def _approve(current: dict[str, Any]) -> dict[str, Any]:
        current = apply_plan_substate_patch(
            current,
            phase="APPROVED",
            plan_hash_at_approval=plan_hash,
            approved_at=now,
            approved_by=approved_by,
            pop_fields=("notice", "last_plan_gate"),
            stamp_orchestration=False,
            mirror_verified_loop=False,
        )

        if start_execute_loop:
            current_loop = dict(current.get("verified_loop") or {})
            current_loop["loop_goal"] = approved
            current_loop["status"] = "running"
            current_loop["iteration"] = 0
            current_loop["verification_attempts"] = 0
            current_loop["oracle_session_id"] = oracle_session_id
            current_loop.pop("circuit_breaker", None)
            current["verified_loop"] = current_loop

            current["session_goal"] = {
                "text": goal_text,
                "set_at": now,
                "updated_at": now,
                "set_by": "agents+human",
            }
            current["goal_loop"] = {
                "enabled": True,
                "status": "open",
                "max_checks": 5,
                "checks": [],
            }
        from agent_lab.runtime.orchestration import stamp_orchestration_state

        return stamp_orchestration_state(current)

    updated = patch_run_meta(session_folder, _approve)

    if start_execute_loop:
        from agent_lab.mission.loop import (
            after_plan_scribe,
            enable_mission_loop,
            start_mission_autonomous_segment,
        )

        enable_mission_loop(session_folder)
        after_plan_scribe(session_folder, md)
        start_mission_autonomous_segment(session_folder)
        updated = read_run_meta(session_folder)

    from agent_lab.runtime.orchestration import stamp_orchestration_on_folder

    stamp_orchestration_on_folder(session_folder)
    updated = read_run_meta(session_folder)

    pw_out = get_plan_workflow(updated)
    loop_out = dict(updated.get("verified_loop") or {})
    return {
        "fast_path": enable_workflow,
        "plan_workflow": pw_out,
        "verified_loop": loop_out,
        "session_goal": updated.get("session_goal"),
        "goal_loop": updated.get("goal_loop"),
        "execute_loop_started": start_execute_loop,
    }


def reject_plan(
    session_folder: Path,
    *,
    note: str = "",
    target_phase: PlanWorkflowPhase = "CLARIFY",
) -> dict[str, Any]:
    allowed = {"CLARIFY", "REFINE", "DRAFT"}
    phase = target_phase if target_phase in allowed else "CLARIFY"

    def _reject(run: RunState) -> RunState:
        patch_kwargs: dict[str, Any] = {}
        if note.strip():
            patch_kwargs["last_reject_note"] = note.strip()[:500]
        run_out = apply_plan_substate_patch(  # type: ignore[assignment]
            run,
            phase=phase,
            pop_fields=("notice", "last_plan_gate"),
            stamp_orchestration=False,
            **patch_kwargs,
        )
        loop = dict(run_out.get("verified_loop") or {})
        loop["status"] = "proposing"
        run_out["verified_loop"] = loop
        from agent_lab.runtime.orchestration import stamp_orchestration_state

        return stamp_orchestration_state(run_out)  # type: ignore[return-value]

    patch_run_meta(session_folder, _reject)
    return get_plan_workflow(read_run_meta(session_folder))
