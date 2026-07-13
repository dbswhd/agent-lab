from __future__ import annotations

import json
from pathlib import Path

from agent_lab.mission.dual_read import evaluate_manifest, inspect_fixture
from agent_lab.mission.activity_queue import ActivityQueue, QueueState, QueuedActivity


ROOT = Path(__file__).resolve().parents[1]


def test_regression_fixtures_are_reported_unmigrated_without_false_parity() -> None:
    report = evaluate_manifest(ROOT, ROOT / "tests" / "fixtures" / "mission-baseline.json")

    assert len(report.results) == 5
    assert all(result.status == "unmigrated" for result in report.results)
    assert report.cutover_ready is False
    assert all(result.journal_present is False for result in report.results)


def test_dual_read_reports_pass_when_fixture_has_matching_journal(tmp_path: Path) -> None:
    folder = tmp_path / "fixture"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps({"plan_workflow": {"phase": "APPROVED"}}),
        encoding="utf-8",
    )
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    journal.parent.mkdir()
    journal.write_text(
        json.dumps(
            {
                "event_id": "e-1",
                "sequence": 1,
                "event_type": "PlanApproved",
                "payload": {},
                "mission_id": "fixture",
                "schema_version": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = inspect_fixture(
        tmp_path,
        {
            "id": "fixture-1",
            "fixture": "fixture",
            "expected_terminal_state": "approved",
        },
    )

    assert result.status == "pass"
    assert result.journal_present is True


def test_dual_read_accepts_activity_queue_evidence_for_completed_step(tmp_path: Path) -> None:
    folder = tmp_path / "fixture"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps({"completed_steps": [{"step": "1"}]}),
        encoding="utf-8",
    )
    ActivityQueue.for_session(folder).enqueue(
        QueuedActivity("recovery-step-1", "fixture", "recovery", 1, "recovery-step-1", QueueState.COMPLETED)
    )

    result = inspect_fixture(
        tmp_path,
        {
            "id": "fixture-1",
            "fixture": "fixture",
            "expected_terminal_state": "partial",
        },
    )

    assert result.status == "pass"
    assert result.journal_present is False
    assert result.activity_queue_present is True
