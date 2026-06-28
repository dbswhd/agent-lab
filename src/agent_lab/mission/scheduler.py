"""Generic mission scheduler — run.json schedules[] (Phase 1)."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agent_lab.daemon_state import mark_scheduler_tick
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.session import SESSIONS_DIR

logger = logging.getLogger("agent_lab.mission.scheduler")

_SCHEDULER_THREAD: threading.Thread | None = None
_SCHEDULER_STOP = threading.Event()
_DEFAULT_INTERVAL_S = 60


def scheduler_interval_s() -> int:
    raw = (os.getenv("AGENT_LAB_MISSION_SCHEDULER_INTERVAL_S") or "").strip()
    try:
        return max(15, min(int(raw), 3600))
    except ValueError:
        return _DEFAULT_INTERVAL_S


def mission_scheduler_enabled() -> bool:
    return (os.getenv("AGENT_LAB_MISSION_SCHEDULER") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _field_matches(field: str, value: int, *, min_v: int, max_v: int) -> bool:
    field = field.strip()
    if field == "*":
        return True
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        if "/" in part:
            base, step_s = part.split("/", 1)
            try:
                step = int(step_s)
            except ValueError:
                continue
            if step <= 0:
                continue
            if base == "*":
                if value % step == 0:
                    return True
                continue
            part = base
        if "-" in part:
            a_s, b_s = part.split("-", 1)
            try:
                lo, hi = int(a_s), int(b_s)
            except ValueError:
                continue
            if lo <= value <= hi:
                return True
            continue
        try:
            if int(part) == value:
                return True
        except ValueError:
            continue
    return False


def cron_matches(cron: str, when: datetime) -> bool:
    """Match 5-field cron: minute hour dom month dow (0=Sun or 7=Sun)."""
    parts = cron.split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    if not _field_matches(minute, when.minute, min_v=0, max_v=59):
        return False
    if not _field_matches(hour, when.hour, min_v=0, max_v=23):
        return False
    if not _field_matches(dom, when.day, min_v=1, max_v=31):
        return False
    if not _field_matches(month, when.month, min_v=1, max_v=12):
        return False
    dow_val = when.isoweekday() % 7  # Sun=0 .. Sat=6
    if not _field_matches(dow, dow_val, min_v=0, max_v=7):
        return False
    return True


def _field_valid(field: str, *, min_v: int, max_v: int) -> bool:
    field = field.strip()
    if not field:
        return False
    if field == "*":
        return True
    for part in field.split(","):
        part = part.strip()
        if not part:
            return False
        if "/" in part:
            base, step_s = part.split("/", 1)
            try:
                if int(step_s) <= 0:
                    return False
            except ValueError:
                return False
            if base == "*":
                continue
            part = base
        if "-" in part:
            a_s, b_s = part.split("-", 1)
            try:
                lo, hi = int(a_s), int(b_s)
            except ValueError:
                return False
            if lo > hi or lo < min_v or hi > max_v:
                return False
            continue
        try:
            val = int(part)
        except ValueError:
            return False
        if val < min_v or val > max_v:
            return False
    return True


def validate_cron(cron: str) -> bool:
    """Strict 5-field cron syntax + range check (minute hour dom month dow).

    Unlike ``cron_matches`` (which silently returns False for malformed cron),
    this rejects bad input up front so the API can 400 instead of saving a
    schedule that never fires.
    """
    parts = str(cron or "").split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    return (
        _field_valid(minute, min_v=0, max_v=59)
        and _field_valid(hour, min_v=0, max_v=23)
        and _field_valid(dom, min_v=1, max_v=31)
        and _field_valid(month, min_v=1, max_v=12)
        and _field_valid(dow, min_v=0, max_v=7)
    )


def _schedule_when(entry: dict[str, Any], *, now: datetime | None = None) -> datetime:
    tz_name = str(entry.get("tz") or "UTC").strip() or "UTC"
    try:
        tz: tzinfo = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    base = now or datetime.now(timezone.utc)
    return base.astimezone(tz)


def schedule_due(entry: dict[str, Any], *, now: datetime | None = None) -> bool:
    if entry.get("enabled") is False:
        return False
    if not str(entry.get("pre_approved_at") or "").strip():
        return False
    cron = str(entry.get("cron") or "").strip()
    if not cron:
        return False
    when = _schedule_when(entry, now=now)
    if not cron_matches(cron, when):
        return False
    day_key = when.strftime("%Y-%m-%d")
    return str(entry.get("last_run_date") or "") != day_key


def list_session_schedules(sessions_dir: Path | None = None) -> list[dict[str, Any]]:
    root = sessions_dir or SESSIONS_DIR
    if root is None or not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        run = read_run_meta(child)
        for entry in run.get("schedules") or []:
            if not isinstance(entry, dict):
                continue
            rows.append(
                {
                    "session_id": child.name,
                    "session_folder": str(child),
                    "schedule": entry,
                }
            )
    return rows


def _apply_schedule_sandbox(folder: Path, schedule_id: str, *, sandbox: bool) -> None:
    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        if sandbox:
            run["schedule_sandbox"] = True
            run["schedule_sandbox_id"] = schedule_id
        else:
            run.pop("schedule_sandbox", None)
            run.pop("schedule_sandbox_id", None)
        return run

    patch_run_meta(folder, _patch)


def _record_schedule_run(
    folder: Path,
    schedule_id: str,
    *,
    day: str,
    status: str = "ok",
    error: str | None = None,
) -> None:
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        schedules = list(run.get("schedules") or [])
        for entry in schedules:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("id") or "") != schedule_id:
                continue
            entry["last_run_status"] = status
            entry["last_run_error"] = error
            if status == "ok":
                entry["last_run_date"] = day
                entry["last_run_at"] = ts
            elif status in ("failed", "blocked"):
                entry["last_failed_at"] = ts
        run["schedules"] = schedules
        return run

    patch_run_meta(folder, _patch)


def run_schedule_entry(
    session_id: str,
    entry: dict[str, Any],
    *,
    sessions_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = sessions_dir or SESSIONS_DIR
    if root is None:
        return {"ok": False, "reason": "sessions_dir_unset", "session_id": session_id}
    folder = root / session_id
    if not folder.is_dir():
        return {"ok": False, "reason": "session_missing", "session_id": session_id}

    schedule_id = str(entry.get("id") or "")
    when = _schedule_when(entry)
    day_key = when.strftime("%Y-%m-%d")
    notify_on_start = bool((entry.get("notify") or {}).get("on_start", True))

    if not force and not schedule_due(entry, now=when):
        return {
            "ok": True,
            "skipped": True,
            "reason": "not_due",
            "session_id": session_id,
            "schedule_id": schedule_id,
        }

    raw_profile = str(entry.get("gate_profile") or entry.get("lane") or "assistant").lower()
    gate_profile = raw_profile if raw_profile in ("dev", "assistant") else "assistant"
    sandbox = bool(entry.get("sandbox"))
    template_id = str(entry.get("template_id") or "").strip()

    from agent_lab.gate_scope import set_gate_profile

    set_gate_profile(folder, gate_profile)  # type: ignore[arg-type]

    template_result: dict[str, Any] | None = None
    tick_result: dict[str, Any] | None = None
    mode = "notify_only"

    if gate_profile == "dev":
        mode = "dev_notify_only"
    else:
        _apply_schedule_sandbox(folder, schedule_id, sandbox=sandbox)
        if template_id:
            try:
                from agent_lab.mission.templates import init_plan_workflow_from_template

                template_result = init_plan_workflow_from_template(
                    folder,
                    template_id,
                    sessions_dir=root,
                )
            except (FileNotFoundError, ValueError) as exc:
                _record_schedule_run(
                    folder,
                    schedule_id,
                    day=day_key,
                    status="failed",
                    error=str(exc),
                )
                return {
                    "ok": False,
                    "session_id": session_id,
                    "schedule_id": schedule_id,
                    "reason": "template_error",
                    "error": str(exc),
                }
            if template_result.get("fast_path") is False:
                from agent_lab.gate_snapshot import compute_gate_snapshot
                from agent_lab.gateway.notify_helpers import notify_gate_blocked

                snap = compute_gate_snapshot(read_run_meta(folder))
                notify_gate_blocked(folder, snap, source="schedule_template_hash_mismatch")
                _record_schedule_run(
                    folder,
                    schedule_id,
                    day=day_key,
                    status="blocked",
                    error="hash_mismatch",
                )
                return {
                    "ok": False,
                    "session_id": session_id,
                    "schedule_id": schedule_id,
                    "reason": "hash_mismatch",
                    "template_result": template_result,
                }

        from agent_lab.mission.tick import run_scheduled_mission_tick

        tick_result = run_scheduled_mission_tick(
            folder,
            schedule_id=schedule_id,
            sandbox=sandbox,
        )
        mode = "assistant_sandbox_tick" if sandbox else "assistant_mission_tick"

    payload: dict[str, Any] = {
        "session_id": session_id,
        "schedule_id": schedule_id,
        "template_id": template_id or None,
        "gate_profile": gate_profile,
        "sandbox": sandbox,
        "cron": entry.get("cron"),
        "mode": mode,
    }
    if template_result is not None:
        payload["template_fast_path"] = template_result.get("fast_path", True)
    if tick_result is not None:
        payload["sandbox_tick"] = tick_result

    notify_result: dict[str, Any] | None = None
    if notify_on_start:
        from agent_lab.gateway.notify_helpers import notify_schedule_tick

        notify_result = notify_schedule_tick(payload)

    _record_schedule_run(folder, schedule_id, day=day_key, status="ok")
    return {
        "ok": True,
        "skipped": False,
        "session_id": session_id,
        "schedule_id": schedule_id,
        "mode": mode,
        "notify": notify_result,
        "template_result": template_result,
        "sandbox_tick": tick_result,
    }


def scheduler_tick(
    *,
    sessions_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """One poll — run due schedules across all sessions.

    Per-schedule failures are isolated and logged so one bad schedule never
    aborts the tick or starves the others.
    """
    runs: list[dict[str, Any]] = []
    try:
        rows = list_session_schedules(sessions_dir)
    except Exception:
        logger.exception("scheduler: list_session_schedules failed")
        rows = []
    for row in rows:
        entry = dict(row["schedule"])
        try:
            result = run_schedule_entry(
                row["session_id"],
                entry,
                sessions_dir=sessions_dir,
                force=force,
            )
        except Exception as exc:
            logger.exception(
                "scheduler: schedule %s in %s failed",
                entry.get("id"),
                row.get("session_id"),
            )
            runs.append(
                {
                    "ok": False,
                    "session_id": row.get("session_id"),
                    "schedule_id": entry.get("id"),
                    "error": str(exc)[:200],
                }
            )
            continue
        if not result.get("skipped"):
            runs.append(result)
    payload = {
        "ok": True,
        "skipped": not runs,
        "runs": runs,
        "checked": len(rows),
    }
    mark_scheduler_tick(payload)
    return payload


def _scheduler_loop() -> None:
    while not _SCHEDULER_STOP.wait(scheduler_interval_s()):
        try:
            scheduler_tick()
        except Exception:
            logger.exception("scheduler tick failed")


def start_mission_scheduler_background() -> bool:
    global _SCHEDULER_THREAD
    if not mission_scheduler_enabled():
        return False
    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return True
    _SCHEDULER_STOP.clear()
    _SCHEDULER_THREAD = threading.Thread(
        target=_scheduler_loop,
        name="mission-scheduler",
        daemon=True,
    )
    _SCHEDULER_THREAD.start()
    return True


def stop_mission_scheduler_background() -> None:
    _SCHEDULER_STOP.set()
