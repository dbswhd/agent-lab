"""Orchestration drift auto-reconcile — Slice F (hint → policy action or inbox)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_lab.env_flags import env_bool
from agent_lab.run.state import RunStateLike
from agent_lab.time_utils import utc_now_iso as _now_iso

_MISSION_CANONICAL_PLAN: dict[str, str] = {
    "MISSION_DEFINE": "INTAKE",
    "CLARIFY": "CLARIFY",
    "DISCUSS": "DRAFT",
    "PLAN_GATE": "HUMAN_PENDING",
    "PLAN_REJECT": "REFINE",
}
_EXECUTE_MISSION_PHASES = frozenset(
    {
        "EXECUTE_QUEUE",
        "DRY_RUN",
        "MERGE_REVIEW",
        "VERIFY",
        "REPAIR",
        "MISSION_DONE",
        "MISSION_PAUSED",
    }
)


def orchestration_drift_reconcile_enabled() -> bool:
    return env_bool("AGENT_LAB_ORCHESTRATION_DRIFT_RECONCILE", default=True)


def orchestration_drift_escalate_after() -> int:
    raw = (os.getenv("AGENT_LAB_ORCHESTRATION_DRIFT_ESCALATE_AFTER") or "3").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def _reconcile_meta(run: RunStateLike) -> dict[str, Any]:
    raw = run.get("orchestration_reconcile")
    return dict(raw) if isinstance(raw, dict) else {}


def _pending_orchestration_drift_inbox(run: RunStateLike) -> bool:
    from agent_lab.human_inbox import inbox_items

    for item in inbox_items(run):
        if item.get("status") != "pending":
            continue
        if item.get("source") == "orchestration_drift":
            return True
    return False


def _action_indices_from_plan_md(plan_md: str) -> list[int]:
    from agent_lab.plan.actions import parse_plan_actions

    return [a.index for a in parse_plan_actions(plan_md or "") if a.executable]


def _apply_mission_phase(run: dict[str, Any], phase: str) -> tuple[dict[str, Any], bool]:
    from agent_lab.core.mission_loop import get_mission_loop

    ml = get_mission_loop(run)
    before = str(ml.get("phase") or "").upper()
    if before == phase.upper():
        return run, False
    ml["phase"] = phase
    run["mission_loop"] = ml
    return run, True


def _apply_mission_execute_queue(run: dict[str, Any], folder: Path) -> tuple[dict[str, Any], bool]:
    from agent_lab.core.mission_loop import get_mission_loop
    from agent_lab.plan.workflow_state import plan_workflow_phase

    if plan_workflow_phase(run).upper() != "APPROVED":
        return run, False

    ml = get_mission_loop(run)
    before = str(ml.get("phase") or "").upper()
    if before == "EXECUTE_QUEUE":
        return run, False

    plan_path = folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    indices = _action_indices_from_plan_md(plan_md)

    ml["phase"] = "EXECUTE_QUEUE"
    ml["pending_action_indices"] = indices
    ml["current_action_index"] = indices[0] if indices else None
    gate = dict(ml.get("plan_gate") or {})
    gate["status"] = "ok"
    gate["last_reject_reason"] = None
    gate["failures"] = []
    ml["plan_gate"] = gate
    run["mission_loop"] = ml
    return run, True


def _apply_plan_canonical_for_mission(run: dict[str, Any], mission_phase: str) -> tuple[dict[str, Any], bool]:
    from agent_lab.plan.workflow_state import apply_plan_substate_patch, plan_workflow_phase

    target = _MISSION_CANONICAL_PLAN.get(mission_phase.upper())
    if mission_phase.upper() in _EXECUTE_MISSION_PHASES:
        target = "APPROVED"
    if not target:
        return run, False
    before = plan_workflow_phase(run).upper()
    if before == target:
        return run, False
    updated = apply_plan_substate_patch(run, phase=target, stamp_orchestration=False)
    return updated, True


def apply_reconcile_hint(
    run: dict[str, Any],
    *,
    folder: Path,
    hint: str,
    plan_substate: str | None,
    mission_phase: str | None,
) -> tuple[dict[str, Any], str | None]:
    """Apply a safe auto-align action for ``hint``. Returns (run, action_name)."""
    from agent_lab.runtime.policy import PolicyEngine

    plan = str(plan_substate or "").upper()
    mission = str(mission_phase or "").upper()

    if hint in {"advance_mission_past_plan_gate", "advance_mission_to_execute_queue"}:
        if plan != "APPROVED":
            return run, None
        if PolicyEngine.execute_block_reason(run):
            return run, None
        updated, changed = _apply_mission_execute_queue(run, folder)
        return (updated, "mission_advance_execute_queue") if changed else (run, None)

    if hint == "advance_plan_substate_or_rewind_mission_to_clarify":
        if plan == "CLARIFY" and mission in {"DISCUSS", "PLAN_GATE"}:
            updated, changed = _apply_mission_phase(run, "CLARIFY")
            return (updated, "mission_rewind_clarify") if changed else (run, None)
        return run, None

    if hint == "approve_plan_or_align_mission_to_discuss":
        if plan in {"DRAFT", "PEER_REVIEW", "REFINE", "HUMAN_PENDING"} and mission in _EXECUTE_MISSION_PHASES:
            updated, changed = _apply_mission_phase(run, "DISCUSS")
            return (updated, "mission_rewind_discuss") if changed else (run, None)
        return run, None

    if hint == "align_plan_substate_with_mission_phase":
        if mission in _EXECUTE_MISSION_PHASES:
            if plan != "APPROVED":
                updated, changed = _apply_mission_phase(run, "DISCUSS")
                return (updated, "mission_rewind_discuss") if changed else (run, None)
            return run, None
        if mission in _MISSION_CANONICAL_PLAN:
            updated, changed = _apply_plan_canonical_for_mission(run, mission)
            return (updated, "plan_align_to_mission") if changed else (run, None)
        return run, None

    return run, None


def _record_reconcile_span(folder: Path, *, action: str, hint: str, orch: dict[str, Any]) -> None:
    try:
        from agent_lab.trace_recorder import record_control_span

        record_control_span(
            folder,
            name="orchestration_drift_reconcile",
            status="ok",
            data={
                "action": action,
                "hint": hint,
                "phase": orch.get("phase"),
                "plan_substate": orch.get("plan_substate"),
                "mission_phase": orch.get("mission_phase"),
                "phase_drift": orch.get("phase_drift"),
            },
        )
    except Exception:
        pass


def _escalate_persistent_drift(
    folder: Path,
    *,
    hint: str,
    drift_reason: str,
    streak: int,
) -> dict[str, Any] | None:
    from agent_lab.human_inbox import append_inbox_item, new_inbox_item
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    run = read_run_meta(folder)
    if _pending_orchestration_drift_inbox(run):
        return None

    prompt = (
        f"Plan substate and mission phase remain out of sync after {streak} reconcile attempts. "
        f"Reason: {drift_reason}. Suggested action: {hint}. "
        "Choose how to proceed."
    )

    def _append(run_in: dict[str, Any]) -> dict[str, Any]:
        item = new_inbox_item(
            kind="question",
            source="orchestration_drift",
            prompt=prompt,
            summary=f"orchestration drift: {drift_reason}",
            options=[
                {"id": "align_mission", "label": "Mission phase 맞추기"},
                {"id": "align_plan", "label": "Plan substate 맞추기"},
                {"id": "defer", "label": "나중에"},
            ],
        )
        return append_inbox_item(run_in, item)

    patch_run_meta(folder, _append)
    return {"escalated": True, "streak": streak, "hint": hint, "drift_reason": drift_reason}


def maybe_reconcile_orchestration_drift(
    folder: Path,
    *,
    orch: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """When drift is detected, auto-align safe cases or escalate to Human Inbox."""
    if not orchestration_drift_reconcile_enabled():
        return None

    from agent_lab.core.mission_loop import get_mission_loop
    from agent_lab.run.meta import patch_run_meta, read_run_meta
    from agent_lab.runtime.orchestration import derive_orchestration_state, stamp_orchestration_state

    run = read_run_meta(folder)
    state = orch if orch is not None else derive_orchestration_state(run)
    if not state.get("phase_drift"):
        if _reconcile_meta(run):

            def _clear(run_in: dict[str, Any]) -> dict[str, Any]:
                run_in.pop("orchestration_reconcile", None)
                return run_in

            patch_run_meta(folder, _clear)
        return None

    ml = get_mission_loop(run)
    if ml.get("circuit_breaker"):
        return {"skipped": True, "reason": "circuit_breaker"}

    hint = str(state.get("reconcile_hint") or "")
    drift_reason = str(state.get("phase_drift_reason") or "")
    if not hint:
        return None

    updated_run, action = apply_reconcile_hint(
        run,
        folder=folder,
        hint=hint,
        plan_substate=state.get("plan_substate"),
        mission_phase=state.get("mission_phase"),
    )

    if action:
        meta = {
            "drift_reason": drift_reason,
            "last_hint": hint,
            "last_action": action,
            "last_at": _now_iso(),
            "streak": 0,
        }

        def _apply(run_in: dict[str, Any]) -> dict[str, Any]:
            run_in.update(updated_run)
            run_in["orchestration_reconcile"] = meta
            return stamp_orchestration_state(run_in)

        patch_run_meta(folder, _apply)
        new_run = read_run_meta(folder)
        new_orch = derive_orchestration_state(new_run)
        _record_reconcile_span(folder, action=action, hint=hint, orch=new_orch)
        if not new_orch.get("phase_drift"):

            def _clear(run_in: dict[str, Any]) -> dict[str, Any]:
                run_in.pop("orchestration_reconcile", None)
                return run_in

            patch_run_meta(folder, _clear)
            return {"applied": True, "action": action, "phase_drift": False}
        meta["streak"] = 1
        patch_run_meta(folder, lambda r: {**r, "orchestration_reconcile": meta})
    else:
        rec = _reconcile_meta(run)
        streak = int(rec.get("streak") or 0) + 1
        if rec.get("drift_reason") != drift_reason:
            streak = 1
        rec = {
            "drift_reason": drift_reason,
            "last_hint": hint,
            "last_action": None,
            "last_at": _now_iso(),
            "streak": streak,
        }
        patch_run_meta(folder, lambda r: {**r, "orchestration_reconcile": rec})

    run_after = read_run_meta(folder)
    streak = int(_reconcile_meta(run_after).get("streak") or 0)
    if streak >= orchestration_drift_escalate_after():
        escalated = _escalate_persistent_drift(
            folder,
            hint=hint,
            drift_reason=drift_reason,
            streak=streak,
        )
        if escalated:
            return {"applied": bool(action), "action": action, "escalated": True, **escalated}

    return {
        "applied": bool(action),
        "action": action,
        "phase_drift": bool(derive_orchestration_state(run_after).get("phase_drift")),
        "streak": streak,
    }
