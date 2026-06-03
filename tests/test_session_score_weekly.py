"""Weekly KPI aggregation and M4 milestone evaluation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from agent_lab.session_score import score_session
from agent_lab.session_score_weekly import (
    aggregate_rates,
    build_weekly_report,
    discover_sessions,
    evaluate_m4_milestones,
    session_anchor_date,
)

ROOT = Path(__file__).resolve().parents[1]
REGRESSION = ROOT / "sessions" / "_regression"


def test_session_anchor_date_from_folder_name():
    folder = REGRESSION / "worktree_merge_ok"
    assert session_anchor_date(folder) == date(2026, 6, 1)


def test_discover_regression_fixtures_in_window():
    found = discover_sessions(
        REGRESSION.parent,
        days=30,
        include_fixtures=True,
        as_of=date(2026, 6, 3),
    )
    names = {item.folder.name for item in found}
    assert "worktree_merge_ok" in names
    assert all(item.folder.parent.name == "_regression" for item in found if item.folder.name == "worktree_merge_ok")


def test_aggregate_m4_pass_on_worktree_fixture_window():
    reports = [
        score_session(REGRESSION / "worktree_merge_ok"),
        score_session(REGRESSION / "objection_blocks_execute"),
    ]
    scores, counts = aggregate_rates(reports)
    m4 = evaluate_m4_milestones(scores, counts)
    assert m4["execute_retry"]["applicable"] is True
    assert m4["execute_retry"]["pass"] is True


def test_m4_fails_high_retry_rate():
    scores = {
        "objection_resolution_rate": 0.9,
        "execute_retry_rate": 0.5,
    }
    counts = {
        "objections": {"total": 10, "resolved": 9, "open": 1},
        "executions": {"terminal": 10, "first_try": 5, "retried": 5},
    }
    m4 = evaluate_m4_milestones(scores, counts)
    assert m4["objection_resolution"]["pass"] is True
    assert m4["execute_retry"]["pass"] is False
    assert m4["overall_pass"] is False


def test_build_weekly_report_includes_summary():
    report = build_weekly_report(
        REGRESSION.parent,
        days=30,
        include_fixtures=True,
        as_of=date(2026, 6, 3),
    )
    assert report["sessions"]
    assert "Weekly KPI" in report["summary_lines"][0]
    assert "m4_milestones" in report
    assert report["aggregate"]["scores"]["execute_retry_rate"] is not None


def test_weekly_report_rolls_up_capability_cwd_asymmetry():
    report = build_weekly_report(
        REGRESSION.parent,
        days=30,
        include_fixtures=True,
        as_of=date(2026, 6, 3),
    )
    scores = report["aggregate"]["scores"]
    counts = report["aggregate"]["counts"]["capability_cwd"]

    assert "asymmetric_capability_cwd_rate" in scores
    assert "specialist_context_recorded_rate" in scores
    assert counts["specialist_contexts"] >= 1
    assert counts["asymmetric"] >= 1
    assert scores["asymmetric_capability_cwd_rate"] is not None
    assert any("specialist cwd asymmetry" in line for line in report["summary_lines"])


def test_execute_retry_rate_on_single_session():
    report = score_session(REGRESSION / "worktree_merge_ok")
    assert report["scores"]["execute_retry_rate"] == 0.0
