from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent_lab.mission.activity_queue import QueuedActivity
from agent_lab.mission.scheduler_shadow import build_scheduler_shadow_report, collect_scheduler_shadow_report


def _row(schedule_id: str = "daily") -> dict[str, object]:
    return {
        "session_id": "session-1",
        "schedule": {
            "id": schedule_id,
            "cron": "* * * * *",
            "pre_approved_at": "2026-07-01T00:00:00Z",
            "gate_profile": "assistant",
            "enabled": True,
        },
    }


def test_shadow_translation_matches_legacy_due_candidate() -> None:
    now = datetime(2026, 7, 13, 12, 30, tzinfo=timezone.utc)

    report = build_scheduler_shadow_report([_row()], now=now)

    assert report.translation_parity is True
    assert report.legacy_due_ids == ("schedule:session-1:daily:2026-07-13",)
    assert report.candidate_ids == report.legacy_due_ids
    assert report.queue_parity is False


def test_shadow_queue_parity_accepts_matching_pending_activity() -> None:
    now = datetime(2026, 7, 13, 12, 30, tzinfo=timezone.utc)
    item = QueuedActivity(
        "schedule:session-1:daily:2026-07-13",
        "session-1",
        "scheduled_mission_tick",
        20,
        "schedule-run:session-1:daily:2026-07-13",
    )

    report = build_scheduler_shadow_report([_row()], (item,), now=now)

    assert report.queue_parity is True
    assert report.missing_queue_ids == ()
    assert report.unexpected_queue_ids == ()


def test_shadow_report_does_not_treat_not_due_or_invalid_rows_as_candidates() -> None:
    now = datetime(2026, 7, 13, 12, 30, tzinfo=timezone.utc)
    not_due = _row("tomorrow")
    not_due_schedule = not_due["schedule"]
    assert isinstance(not_due_schedule, dict)
    not_due_schedule["cron"] = "0 0 * * *"
    invalid = _row("")

    report = build_scheduler_shadow_report([not_due, invalid], now=now)

    assert report.candidate_ids == ()
    assert report.invalid_rows == ("session-1:<missing>",)
    assert report.translation_parity is False


def test_collect_shadow_report_does_not_enqueue_or_mutate_legacy_session(tmp_path: Path) -> None:
    folder = tmp_path / "session-1"
    folder.mkdir()
    schedule = _row()["schedule"]
    (folder / "run.json").write_text(json.dumps({"schedules": [schedule]}), encoding="utf-8")

    report = collect_scheduler_shadow_report(
        tmp_path,
        now=datetime(2026, 7, 13, 12, 30, tzinfo=timezone.utc),
    )

    assert report.candidate_ids == ("schedule:session-1:daily:2026-07-13",)
    assert not (folder / ".agent-lab" / "activities.json").exists()
