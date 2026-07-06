"""Human-approved plan snapshots before thin execute dry-run (Sprint B)."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunState, RunStateLike

from agent_lab.plan.actions import PlanAction
from agent_lab.run.meta import patch_run_meta, read_run_meta

RUN_PENDING_PLANS_KEY = "pending_plans"
DEFAULT_MAX_TASKS_PER_TURN = 8


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pending_id() -> str:
    return f"pp-{uuid.uuid4().hex[:10]}"


def max_tasks_per_turn() -> int:
    raw = os.getenv("AGENT_LAB_MAX_TASKS_PER_TURN", str(DEFAULT_MAX_TASKS_PER_TURN)).strip()
    try:
        return max(1, min(32, int(raw)))
    except ValueError:
        return DEFAULT_MAX_TASKS_PER_TURN


def plan_content_hash(plan_md: str) -> str:
    return hashlib.sha256((plan_md or "").encode("utf-8")).hexdigest()[:16]


class PlanSnapshotRequired(Exception):
    """Raised when dry-run needs Human approval of a frozen plan excerpt first."""

    def __init__(self, pending_plan: dict[str, Any]):
        self.pending_plan = pending_plan
        super().__init__("plan_snapshot_approval_required")


def list_pending_plans(run_meta: RunStateLike | None) -> list[dict[str, Any]]:
    if not run_meta:
        return []
    raw = run_meta.get(RUN_PENDING_PLANS_KEY)
    if not isinstance(raw, list):
        return []
    return [p for p in raw if isinstance(p, dict)]


def _action_snapshot_text(action: PlanAction) -> str:
    return (f"무엇을: {action.what}\n어디서: {action.where}\n검증: {action.verify}\n").strip()


def find_approved_snapshot(
    run_meta: RunStateLike,
    action_key: str,
    plan_md: str,
) -> dict[str, Any] | None:
    plan_hash = plan_content_hash(plan_md)
    for row in reversed(list_pending_plans(run_meta)):
        if row.get("status") != "approved":
            continue
        if str(row.get("action_key") or "") != action_key:
            continue
        if str(row.get("plan_hash") or "") != plan_hash:
            continue
        return row
    return None


def create_pending_plan_snapshot(
    action: PlanAction,
    plan_md: str,
) -> dict[str, Any]:
    return {
        "id": _pending_id(),
        "status": "pending_approval",
        "action_key": f"{action.kind}:{action.index}",
        "action_index": action.index,
        "action_kind": action.kind,
        "action_id": action.action_id,
        "action_what": action.what,
        "action_where": action.where,
        "action_verify": action.verify,
        "snapshot_text": _action_snapshot_text(action),
        "plan_hash": plan_content_hash(plan_md),
        "created_at": _now(),
        "approved_at": None,
    }


def _whole_plan_approval_matches(run: RunStateLike, plan_md: str) -> bool:
    workflow = run.get("plan_workflow")
    if not isinstance(workflow, dict):
        return False
    return (
        workflow.get("enabled") is True
        and workflow.get("phase") == "APPROVED"
        and workflow.get("plan_hash_at_approval") == plan_content_hash(plan_md)
    )


def ensure_plan_snapshot_approved(
    folder: Path,
    action: PlanAction,
    plan_md: str,
) -> dict[str, Any]:
    """Return approved snapshot row or persist a new pending plan and raise."""
    run = read_run_meta(folder)
    action_key = f"{action.kind}:{action.index}"
    approved = find_approved_snapshot(run, action_key, plan_md)
    if approved is not None:
        return approved

    pending = create_pending_plan_snapshot(action, plan_md)
    if _whole_plan_approval_matches(run, plan_md):
        approved_at = _now()
        pending["status"] = "approved"
        pending["approved_at"] = approved_at
        pending["updated_at"] = approved_at
        pending["approved_by"] = "whole_plan"

        def _record_whole_plan_approval(current: dict[str, Any]) -> dict[str, Any]:
            plans = list_pending_plans(current)
            plans.append(pending)
            current[RUN_PENDING_PLANS_KEY] = plans
            return current

        patch_run_meta(folder, _record_whole_plan_approval)
        return pending

    def _upsert(run: RunState) -> RunState:
        plans = list_pending_plans(run)
        for row in plans:
            if row.get("action_key") == action_key and row.get("status") == "pending_approval":
                row["status"] = "superseded"
                row["updated_at"] = _now()
        plans.append(pending)
        run[RUN_PENDING_PLANS_KEY] = plans
        return run

    patch_run_meta(folder, _upsert)
    raise PlanSnapshotRequired(pending)


def approve_pending_plan(folder: Path, pending_id: str) -> dict[str, Any]:
    run = read_run_meta(folder)
    plans = list_pending_plans(run)
    target = next((p for p in plans if p.get("id") == pending_id), None)
    if target is None:
        raise ValueError(f"pending plan not found: {pending_id}")
    if target.get("status") != "pending_approval":
        raise ValueError(f"pending plan not awaiting approval: {target.get('status')}")

    approved_at = _now()
    target["status"] = "approved"
    target["approved_at"] = approved_at
    target["updated_at"] = approved_at
    target["approved_by"] = "human"

    def _write(run: RunState) -> RunState:
        run[RUN_PENDING_PLANS_KEY] = plans
        return run

    patch_run_meta(folder, _write)
    return dict(target)


def reject_pending_plan(folder: Path, pending_id: str) -> dict[str, Any]:
    run = read_run_meta(folder)
    plans = list_pending_plans(run)
    target = next((p for p in plans if p.get("id") == pending_id), None)
    if target is None:
        raise ValueError(f"pending plan not found: {pending_id}")
    target["status"] = "rejected"
    target["updated_at"] = _now()

    def _write(run: RunState) -> RunState:
        run[RUN_PENDING_PLANS_KEY] = plans
        return run

    patch_run_meta(folder, _write)
    return dict(target)


def pending_plans_public_payload(run_meta: RunStateLike | None) -> dict[str, Any]:
    plans = list_pending_plans(run_meta)
    awaiting = [p for p in plans if p.get("status") == "pending_approval"]
    return {
        "pending_plans": plans,
        "awaiting_approval": awaiting,
        "max_tasks_per_turn": max_tasks_per_turn(),
    }
