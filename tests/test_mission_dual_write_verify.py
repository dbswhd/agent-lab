"""Read-only legacy/Mission parity verification query."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.mission_dual_write_verify import run_verification


def _write_run(folder: Path, run: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(json.dumps(run, ensure_ascii=False) + "\n", encoding="utf-8")


def test_unmigrated_session_reported_without_findings(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    _write_run(sessions_root / "sess-1", {"topic": "sess-1"})

    report = run_verification(sessions_root, only_session=None, cohort_only=False)

    assert report["checked"] == 1
    assert report["migrated_count"] == 0
    assert report["hard_mismatch_count"] == 0
    assert report["results"][0]["severity"] == "not_migrated"


def test_matching_merged_commit_and_oracle_verdict_is_ok(tmp_path: Path) -> None:
    from agent_lab.mission.application import MissionApplication
    from agent_lab.mission.kernel import ApproveDiff, MarkDiffReady, OracleVerdict, RecordMerge, RecordOracle, StartExecution

    sessions_root = tmp_path / "sessions"
    folder = sessions_root / "sess-ok"
    folder.mkdir(parents=True)
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    _write_run(
        folder,
        {
            "executions": [
                {
                    "id": "exec-1",
                    "status": "merged",
                    "merge": {"commit_sha": "abc123"},
                    "oracle": {"verdict": "pass"},
                }
            ]
        },
    )
    app = MissionApplication(folder, "ship")
    app.approve_plan()
    repo = app.repository
    repo.dispatch(StartExecution())
    repo.dispatch(MarkDiffReady())
    repo.dispatch(ApproveDiff())
    repo.dispatch(RecordMerge("abc123"))
    repo.dispatch(RecordOracle(OracleVerdict.PASS, "ok"))

    report = run_verification(sessions_root, only_session=None, cohort_only=False)

    result = report["results"][0]
    assert result["migrated"] is True
    assert result["severity"] == "ok"
    assert result["findings"] == []
    assert report["hard_mismatch_count"] == 0


def test_diverging_merge_commit_is_hard_mismatch(tmp_path: Path) -> None:
    from agent_lab.mission.application import MissionApplication
    from agent_lab.mission.kernel import ApproveDiff, MarkDiffReady, RecordMerge, StartExecution

    sessions_root = tmp_path / "sessions"
    folder = sessions_root / "sess-diverge"
    folder.mkdir(parents=True)
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    _write_run(folder, {"executions": [{"id": "exec-1", "status": "merged", "merge": {"commit_sha": "legacy-sha"}}]})
    app = MissionApplication(folder, "ship")
    app.approve_plan()
    repo = app.repository
    repo.dispatch(StartExecution())
    repo.dispatch(MarkDiffReady())
    repo.dispatch(ApproveDiff())
    repo.dispatch(RecordMerge("mission-sha"))  # deliberately different from legacy

    report = run_verification(sessions_root, only_session=None, cohort_only=False)

    result = report["results"][0]
    assert result["severity"] == "hard_mismatch"
    assert any(f["dimension"] == "merge_commit_sha" and f["severity"] == "hard_mismatch" for f in result["findings"])
    assert report["hard_mismatch_count"] == 1
    assert report["hard_mismatch_sessions"] == ["sess-diverge"]


def test_mission_not_yet_recorded_merge_is_behind_not_hard_mismatch(tmp_path: Path) -> None:
    from agent_lab.mission.application import MissionApplication

    sessions_root = tmp_path / "sessions"
    folder = sessions_root / "sess-behind"
    folder.mkdir(parents=True)
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    _write_run(folder, {"executions": [{"id": "exec-1", "status": "merged", "merge": {"commit_sha": "legacy-only-sha"}}]})
    MissionApplication(folder, "ship").approve_plan()  # Mission never advanced past READY_TO_EXECUTE

    report = run_verification(sessions_root, only_session=None, cohort_only=False)

    result = report["results"][0]
    assert result["severity"] == "mission_behind"
    assert report["hard_mismatch_count"] == 0
    assert any(f["dimension"] == "merge_commit_sha" and f["severity"] == "mission_behind" for f in result["findings"])


def test_pending_inbox_item_created_via_real_path_is_no_longer_a_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: create_inbox_item() now carries a dual-write hook
    (mirror_inbox_creation), so a real, unscripted inbox pause opens a Mission
    execution gate for that exact item id — this used to be a hard_mismatch
    (Mission never entered AWAITING_HUMAN at all), see
    docs/redesign-2026-07/dual-write-observability-and-verification-2026-07-13.md
    and docs/redesign-2026-07/execution-gate-design-draft-2026-07-13.md.
    """
    from agent_lab.human_inbox import create_inbox_item
    from agent_lab.mission.application import MissionApplication

    sessions_root = tmp_path / "sessions"
    folder = sessions_root / "sess-inbox"
    folder.mkdir(parents=True)
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    MissionApplication(folder, "ship").approve_plan()
    item = create_inbox_item(folder, kind="question", source="manual", prompt="Proceed?")

    report = run_verification(sessions_root, only_session=None, cohort_only=False)

    result = report["results"][0]
    assert result["mission_state"] == "READY_TO_EXECUTE"  # unchanged — gates are observational
    assert result["operational_status"] == "WAITING_FOR_HUMAN"  # composite projection picks it up
    assert result["open_gate_ids"] == [item["id"]]
    assert result["severity"] == "ok"
    assert result["findings"] == []


def test_mission_gate_open_but_legacy_item_missing_is_hard_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mission opened a gate but the legacy item isn't (or is no longer) pending —
    the 'stale_in_mission' direction of the item-level diff."""
    from agent_lab.mission.application import MissionApplication
    from agent_lab.mission.kernel import OpenExecutionGate

    sessions_root = tmp_path / "sessions"
    folder = sessions_root / "sess-stale-gate"
    folder.mkdir(parents=True)
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")
    app = MissionApplication(folder, "ship")
    app.approve_plan()
    app.repository.dispatch(OpenExecutionGate("gate-orphan"))

    report = run_verification(sessions_root, only_session=None, cohort_only=False)

    result = report["results"][0]
    assert result["severity"] == "hard_mismatch"
    detail = next(f for f in result["findings"] if f["dimension"] == "human_inbox")
    assert "gate-orphan" in detail["detail"]


def test_terminal_mission_with_open_gate_is_orphaned_gate_review_needed(tmp_path: Path) -> None:
    """Terminal status always wins (operational_status stays COMPLETED), but a
    lingering open gate on a finished mission is a data-hygiene signal worth
    surfacing — not a hard_mismatch (nothing is factually wrong with the state)."""
    from agent_lab.mission.application import MissionApplication
    from agent_lab.mission.kernel import (
        ApproveDiff,
        MarkDiffReady,
        OpenExecutionGate,
        OracleVerdict,
        RecordMerge,
        RecordOracle,
        StartExecution,
    )

    sessions_root = tmp_path / "sessions"
    folder = sessions_root / "sess-terminal-orphan"
    folder.mkdir(parents=True)
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")
    app = MissionApplication(folder, "ship")
    app.approve_plan()
    repo = app.repository
    repo.dispatch(OpenExecutionGate("gate-never-closed"))
    for command in (StartExecution(), MarkDiffReady(), ApproveDiff(), RecordMerge("sha-1")):
        repo.dispatch(command)
    repo.dispatch(RecordOracle(OracleVerdict.PASS, "green"))

    report = run_verification(sessions_root, only_session=None, cohort_only=False)

    result = report["results"][0]
    assert result["mission_state"] == "SUCCEEDED"
    assert result["operational_status"] == "COMPLETED"
    assert result["severity"] == "review_needed"
    orphan = next(f for f in result["findings"] if f["dimension"] == "orphaned_gate")
    assert "gate-never-closed" in orphan["detail"]
    assert report["hard_mismatch_count"] == 0  # review_needed never trips the exit code


def test_cohort_only_scopes_to_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_root = tmp_path / "sessions"
    _write_run(sessions_root / "in-cohort", {"topic": "in-cohort"})
    _write_run(sessions_root / "outside-cohort", {"topic": "outside-cohort"})
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", "in-cohort")

    report = run_verification(sessions_root, only_session=None, cohort_only=True)

    assert report["checked"] == 1
    assert report["results"][0]["session_id"] == "in-cohort"


def test_single_session_flag_checks_only_that_session(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    _write_run(sessions_root / "a", {"topic": "a"})
    _write_run(sessions_root / "b", {"topic": "b"})

    report = run_verification(sessions_root, only_session="a", cohort_only=False)

    assert report["checked"] == 1
    assert report["results"][0]["session_id"] == "a"


def test_verify_is_read_only(tmp_path: Path) -> None:
    from agent_lab.human_inbox import create_inbox_item
    from agent_lab.mission.application import MissionApplication

    sessions_root = tmp_path / "sessions"
    folder = sessions_root / "sess-untouched"
    folder.mkdir(parents=True)
    (folder / "plan.md").write_text("# Plan\n\n- ship", encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")
    MissionApplication(folder, "ship").approve_plan()
    create_inbox_item(folder, kind="question", source="manual", prompt="Proceed?")
    before_run = (folder / "run.json").read_text(encoding="utf-8")
    before_journal = (folder / ".agent-lab" / "mission-events.jsonl").read_text(encoding="utf-8")

    run_verification(sessions_root, only_session=None, cohort_only=False)

    assert (folder / "run.json").read_text(encoding="utf-8") == before_run
    assert (folder / ".agent-lab" / "mission-events.jsonl").read_text(encoding="utf-8") == before_journal
