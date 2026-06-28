"""CI-facing score_session coverage for regression fixtures."""

from __future__ import annotations

from pathlib import Path

from agent_lab.session.score import score_session

ROOT = Path(__file__).resolve().parents[1]
REGRESSION = ROOT / "sessions" / "_regression"

REQUIRED_SCORE_KEYS = {
    "objection_resolution_rate",
    "execute_first_try_rate",
    "execute_retry_rate",
    "ref_validity_rate",
    "duplicate_speech_rate",
    "partial_turn_rate",
    "worktree_usage_rate",
    "snapshot_override_rate",
    "merge_first_success_rate",
    "merge_conflict_rate",
    "specialist_context_recorded",
    "asymmetric_capability_cwd",
    "capability_cwd_agent_count",
}

REQUIRED_COUNT_KEYS = {
    "objections",
    "executions",
    "execute_merge",
    "turns",
    "capability_cwd",
    "plan_refs",
    "duplicate_speech",
}


def test_score_session_regression_fixtures_do_not_crash():
    folders = sorted(p for p in REGRESSION.iterdir() if (p / "run.json").is_file())
    assert folders, "missing regression fixtures"

    for folder in folders:
        report = score_session(folder)
        assert report["session_id"] == folder.name
        assert REQUIRED_SCORE_KEYS <= set(report["scores"])
        assert REQUIRED_COUNT_KEYS <= set(report["counts"])
        assert isinstance(report["summary_lines"], list)
        assert report["summary_lines"]


def test_score_session_worktree_merge_ok_kpis():
    report = score_session(REGRESSION / "worktree_merge_ok")
    scores = report["scores"]

    assert scores["worktree_usage_rate"] == 1.0
    assert scores["merge_first_success_rate"] == 1.0
    assert scores["merge_conflict_rate"] == 0.0
    assert scores["partial_turn_rate"] == 0.0
