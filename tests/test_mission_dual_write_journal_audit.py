from __future__ import annotations

import json
from pathlib import Path

from scripts.mission_dual_write_journal_audit import run_audit


def test_journal_audit_flags_conflicting_idempotency_keys(tmp_path: Path) -> None:
    folder = tmp_path / "sess-a"
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    journal.parent.mkdir(parents=True)
    lines = [
        {
            "event_id": "evt-1",
            "sequence": 1,
            "event_type": "OpenPlan",
            "payload": {"plan_hash": "a"},
            "idempotency_key": "plan-open:a",
            "mission_id": "sess-a",
            "schema_version": 1,
        },
        {
            "event_id": "evt-2",
            "sequence": 2,
            "event_type": "OpenPlan",
            "payload": {"plan_hash": "b"},
            "idempotency_key": "plan-open:a",
            "mission_id": "sess-a",
            "schema_version": 1,
        },
    ]
    journal.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in lines), encoding="utf-8")

    report = run_audit(tmp_path, cohort_only=False)

    assert report["duplicate_count"] == 1
    assert report["duplicate_sessions"] == ["sess-a"]
    finding = report["results"][0]["findings"][0]
    assert finding["severity"] == "duplicate"


def test_journal_audit_allows_identical_idempotent_replay(tmp_path: Path) -> None:
    folder = tmp_path / "sess-b"
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    journal.parent.mkdir(parents=True)
    lines = [
        {
            "event_id": "evt-1",
            "sequence": 1,
            "event_type": "OpenPlan",
            "payload": {"plan_hash": "same"},
            "idempotency_key": "plan-open:same",
            "mission_id": "sess-b",
            "schema_version": 1,
        },
        {
            "event_id": "evt-2",
            "sequence": 2,
            "event_type": "OpenPlan",
            "payload": {"plan_hash": "same"},
            "idempotency_key": "plan-open:same",
            "mission_id": "sess-b",
            "schema_version": 1,
        },
    ]
    journal.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in lines), encoding="utf-8")

    report = run_audit(tmp_path, cohort_only=False)

    assert report["duplicate_count"] == 0
    findings = report["results"][0]["findings"]
    assert any(f["severity"] == "review_needed" for f in findings)
