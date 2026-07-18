"""Scheduled mission tick — harvest + mission_loop conductor (Mission OS M2b)."""

from __future__ import annotations

from agent_lab.time_utils import utc_now_iso_seconds
from agent_lab.run.state import RunStateLike
from pathlib import Path
from typing import Any

from agent_lab.run.meta import patch_run_meta, read_run_meta

_EARLY_MISSION_PHASES = frozenset({"DISCUSS", "PLAN_GATE", "PLAN_REJECT", "MISSION_DEFINE"})
_MAX_SCHEDULED_CONDUCTOR_STEPS = 8
_TERMINAL_MISSION_PHASES = frozenset({"MISSION_DONE", "MISSION_PAUSED", "DISCUSS", "PLAN_REJECT"})


def _harvest_plan_questions(
    folder: Path,
    run_meta: RunStateLike,
    *,
    plan_md: str,
) -> list[dict[str, Any]]:
    if not plan_md.strip():
        return []
    from agent_lab.inbox.harvest import harvest_discuss_questions

    return harvest_discuss_questions(
        run_meta,
        [],
        plan_md=plan_md,
        mode="discuss",
        session_id=folder.name,
    )


def _notify_harvest_items(folder: Path, items: list[dict[str, Any]]) -> None:
    for item in items:
        try:
            from agent_lab.human_inbox import fan_out_inbox_item

            fan_out_inbox_item(folder.name, item)
        except Exception:
            pass


def _stamp_schedule_meta(run_meta: RunStateLike, schedule_id: str) -> dict[str, Any]:
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(
        run_meta,
        mission_schedule={
            **dict(run_meta.get("mission_schedule") or {}),
            "last_sandbox_tick_at": utc_now_iso_seconds(),
            "last_schedule_id": schedule_id,
        },
    )
    return run_meta


def _run_mission_loop_conductor(
    folder: Path,
    *,
    sandbox: bool,
) -> dict[str, Any]:
    from agent_lab.mission.board import record_autorun_tick, sync_turn_budget_from_mission
    from agent_lab.mission.loop import (
        get_mission_loop,
        mission_autorun_enabled,
        run_plan_gate,
        _scheduled_autorun_allowed,
    )
    from agent_lab.mission.advance import maybe_advance_mission

    run = read_run_meta(folder)
    ml = get_mission_loop(run)
    if not ml.get("enabled"):
        return {"skipped": True, "reason": "mission_loop_disabled"}

    plan_path = folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    phase = str(ml.get("phase") or "")
    steps: list[dict[str, Any]] = []

    if plan_md.strip() and phase in _EARLY_MISSION_PHASES:
        gate = run_plan_gate(folder, plan_md)
        steps.append({"plan_gate": gate})
        ml = get_mission_loop(read_run_meta(folder))
        phase = str(ml.get("phase") or "")

    if sandbox:
        record_autorun_tick(folder)
        sync_turn_budget_from_mission(folder)
        ml = get_mission_loop(read_run_meta(folder))
        phase = str(ml.get("phase") or "")
        if phase in {"EXECUTE_QUEUE", "REPAIR", "DRY_RUN"}:
            return {
                "skipped": True,
                "reason": "schedule_sandbox_read_only",
                "phase": phase,
                "autorun": mission_autorun_enabled(ml),
                "steps": steps,
            }
        return {
            "status": "sandbox_conductor_tick",
            "phase": phase,
            "autorun": mission_autorun_enabled(ml),
            "steps": steps,
        }

    if not _scheduled_autorun_allowed(run, ml, scheduled=True):
        record_autorun_tick(folder)
        sync_turn_budget_from_mission(folder)
        return {
            "skipped": True,
            "reason": "autorun_off",
            "phase": phase,
            "steps": steps,
        }

    conductor_steps: list[dict[str, Any]] = []
    last: dict[str, Any] = {"skipped": True, "reason": "no_advance"}
    last_progress: dict[str, Any] | None = None
    for _ in range(_MAX_SCHEDULED_CONDUCTOR_STEPS):
        advance = maybe_advance_mission(folder, scheduled=True)
        conductor_steps.append(advance)
        last = advance
        if not advance.get("skipped") and advance.get("status") != "error":
            last_progress = advance
        if advance.get("skipped") or advance.get("status") == "error":
            break
        ml = get_mission_loop(read_run_meta(folder))
        phase = str(ml.get("phase") or "")
        if phase in _TERMINAL_MISSION_PHASES:
            break

    summary = dict(last_progress or last)
    summary["conductor_steps"] = conductor_steps
    summary["phase"] = get_mission_loop(read_run_meta(folder)).get("phase")
    summary["steps"] = steps
    return summary


def run_scheduled_mission_tick(
    folder: Path,
    *,
    schedule_id: str,
    sandbox: bool = True,
) -> dict[str, Any]:
    """Cron tick: plan harvest + mission_loop conductor (sandbox skips execute)."""
    run = read_run_meta(folder)
    if sandbox and not run.get("schedule_sandbox"):
        return {"ok": False, "reason": "sandbox_not_active", "schedule_id": schedule_id}

    plan_path = folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    created: list[dict[str, Any]] = []

    def _tick(run_meta: RunStateLike) -> dict[str, Any]:
        nonlocal created
        from agent_lab.run.meta import stamp_run_meta

        stamp_run_meta(run_meta, _session_folder=str(folder.resolve()), _session_id=folder.name)
        created = _harvest_plan_questions(folder, run_meta, plan_md=plan_md)
        return _stamp_schedule_meta(run_meta, schedule_id)

    patch_run_meta(folder, _tick)
    _notify_harvest_items(folder, created)

    mission_loop = _run_mission_loop_conductor(folder, sandbox=sandbox)
    return {
        "ok": True,
        "schedule_id": schedule_id,
        "sandbox": sandbox,
        "harvested": len(created),
        "mission_loop": mission_loop,
        "read_only": sandbox,
    }


def run_mission_sandbox_tick(
    folder: Path,
    *,
    schedule_id: str,
) -> dict[str, Any]:
    """Backward-compatible alias — harvest + sandbox mission conductor."""
    return run_scheduled_mission_tick(folder, schedule_id=schedule_id, sandbox=True)
