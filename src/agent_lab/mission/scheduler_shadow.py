from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.mission.activity_queue import ActivityQueue, QueueState, QueuedActivity
from agent_lab.mission.scheduler import _schedule_when, list_session_schedules, schedule_due


@dataclass(frozen=True, slots=True)
class SchedulerCandidate:
    activity: QueuedActivity
    session_id: str
    schedule_id: str
    day_key: str


@dataclass(frozen=True, slots=True)
class SchedulerShadowReport:
    checked: int
    legacy_due_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    invalid_rows: tuple[str, ...]
    queue_pending_ids: tuple[str, ...]
    missing_queue_ids: tuple[str, ...]
    unexpected_queue_ids: tuple[str, ...]
    translation_parity: bool
    queue_parity: bool


def _candidate(row: dict[str, Any], *, now: datetime) -> SchedulerCandidate | None:
    session_id = str(row.get("session_id") or "").strip()
    schedule = row.get("schedule")
    if not session_id or not isinstance(schedule, dict) or not schedule_due(schedule, now=now):
        return None
    schedule_id = str(schedule.get("id") or "").strip()
    if not schedule_id:
        return None
    day_key = _schedule_when(schedule, now=now).strftime("%Y-%m-%d")
    activity_id = f"schedule:{session_id}:{schedule_id}:{day_key}"
    idempotency_key = f"schedule-run:{session_id}:{schedule_id}:{day_key}"
    priority = 20 if str(schedule.get("gate_profile") or "assistant") == "assistant" else 10
    activity = QueuedActivity(
        activity_id,
        session_id,
        "scheduled_mission_tick",
        priority,
        idempotency_key,
    )
    return SchedulerCandidate(activity, session_id, schedule_id, day_key)


def build_scheduler_shadow_report(
    rows: list[dict[str, Any]],
    queue_items: tuple[QueuedActivity, ...] = (),
    *,
    now: datetime,
) -> SchedulerShadowReport:
    candidates: list[SchedulerCandidate] = []
    invalid: list[str] = []
    for row in rows:
        candidate = _candidate(row, now=now)
        schedule = row.get("schedule")
        schedule_id = str(schedule.get("id") or "") if isinstance(schedule, dict) else ""
        if candidate is None:
            if isinstance(schedule, dict) and schedule_due(schedule, now=now):
                invalid.append(f"{row.get('session_id', '')}:{schedule_id or '<missing>'}")
            continue
        candidates.append(candidate)

    candidate_ids = tuple(candidate.activity.activity_id for candidate in candidates)
    due_ids = tuple(candidate_ids)
    unique_candidates = len(set(candidate_ids)) == len(candidate_ids)
    pending_states = frozenset({QueueState.QUEUED, QueueState.CLAIMED, QueueState.NEEDS_RECONCILE})
    pending_ids = tuple(item.activity_id for item in queue_items if item.state in pending_states)
    missing = tuple(sorted(set(candidate_ids) - set(pending_ids)))
    unexpected = tuple(sorted(set(pending_ids) - set(candidate_ids)))
    return SchedulerShadowReport(
        checked=len(rows),
        legacy_due_ids=due_ids,
        candidate_ids=candidate_ids,
        invalid_rows=tuple(sorted(invalid)),
        queue_pending_ids=tuple(sorted(pending_ids)),
        missing_queue_ids=missing,
        unexpected_queue_ids=unexpected,
        translation_parity=unique_candidates and not invalid,
        queue_parity=not missing and not unexpected,
    )


def collect_scheduler_shadow_report(
    sessions_dir: Path | None = None,
    *,
    now: datetime | None = None,
) -> SchedulerShadowReport:
    rows = list_session_schedules(sessions_dir)
    queue_items: list[QueuedActivity] = []
    for row in rows:
        folder_text = row.get("session_folder")
        if not isinstance(folder_text, str):
            continue
        folder = Path(folder_text)
        queue_path = folder / ".agent-lab" / "activities.json"
        if queue_path.is_file():
            queue_items.extend(ActivityQueue.for_session(folder).snapshot())
    return build_scheduler_shadow_report(
        rows,
        tuple(queue_items),
        now=now or datetime.now(timezone.utc),
    )
