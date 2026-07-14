from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.mission_dual_write_journal_audit import run_audit


def _run_audit_cli(sessions_root: Path, *, env: dict[str, str | None]) -> subprocess.CompletedProcess[str]:
    from agent_lab.subprocess_env import subprocess_env

    child_env = subprocess_env()
    for key, value in env.items():
        if value is None:
            child_env.pop(key, None)
        else:
            child_env[key] = value
    return subprocess.run(
        [sys.executable, "scripts/mission_dual_write_journal_audit.py", "--sessions", str(sessions_root), "--cohort"],
        cwd=Path(__file__).resolve().parents[1],
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )


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


def test_journal_audit_counts_invalid_json_as_error(tmp_path: Path) -> None:
    folder = tmp_path / "sess-invalid"
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text("{not-json}\n", encoding="utf-8")

    report = run_audit(tmp_path, cohort_only=False)

    assert report["checked"] == 1
    assert report["invalid_json"] == 1
    assert report["error_count"] == 0
    assert report["duplicate_count"] == 0
    assert report["results"][0]["invalid_json"] == 1


def test_journal_audit_reports_missing_session_without_silent_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", "missing")

    report = run_audit(tmp_path, cohort_only=True)

    assert report["checked"] == 1
    assert report["not_found"] == 1
    assert report["error_count"] == 1
    assert "matched no session" in report["errors"][0]


@pytest.mark.parametrize("allowlist", [None, ""])
def test_journal_audit_cohort_empty_allowlist_fails_closed_with_explicit_error(tmp_path: Path, allowlist: str | None) -> None:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()

    proc = _run_audit_cli(sessions_root, env={"AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS": allowlist})

    assert proc.returncode != 0
    report = json.loads(proc.stdout)
    assert report["error_count"] == 1
    assert any("non-empty" in error for error in report["errors"])


def test_journal_audit_cohort_allowlist_with_no_matched_sessions_fails_closed(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()

    proc = _run_audit_cli(sessions_root, env={"AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS": "missing-session"})

    assert proc.returncode != 0
    report = json.loads(proc.stdout)
    assert report["not_found"] == 1
    assert report["error_count"] == 1
    assert any("matched no session" in error for error in report["errors"])


def test_journal_audit_sequence_corruption_counts_as_error_and_duplicate(tmp_path: Path) -> None:
    folder = tmp_path / "sess-sequence"
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text(
        "\n".join(
            json.dumps(
                {
                    "event_id": f"evt-{sequence}",
                    "sequence": sequence,
                    "event_type": "OpenPlan",
                    "payload": {"sequence": sequence},
                }
            )
            for sequence in (1, 3)
        )
        + "\n",
        encoding="utf-8",
    )

    report = run_audit(tmp_path, cohort_only=False)

    assert report["error_count"] == 1
    assert report["duplicate_count"] == 1
    finding = next(f for f in report["results"][0]["findings"] if f["dimension"] == "sequence")
    assert finding["severity"] == "duplicate"
