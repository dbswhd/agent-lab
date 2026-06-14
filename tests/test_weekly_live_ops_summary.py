"""Weekly ops report live Tier B/C summary discovery."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from agent_lab.session_score_weekly import (
    build_weekly_report,
    discover_live_ops_reports,
    format_weekly_report_markdown,
)

ROOT = Path(__file__).resolve().parents[1]
REGRESSION = ROOT / "sessions" / "_regression"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_discover_live_ops_reports_returns_latest_per_kind(tmp_path: Path):
    reports = tmp_path / "_reports"
    _write_json(
        reports / "live-worktree-2026-06-01.json",
        {
            "kind": "live_cursor_worktree_dry_run",
            "status": "go",
            "started_at": "2026-06-01T01:00:00+00:00",
            "finished_at": "2026-06-01T01:01:00+00:00",
            "preflight": {"ready": True},
        },
    )
    _write_json(
        reports / "live-worktree-2026-06-03.json",
        {
            "kind": "live_cursor_worktree_dry_run",
            "status": "skipped",
            "finished_at": "2026-06-03T01:01:00+00:00",
            "preflight": {"ready": False},
        },
    )
    _write_json(
        reports / "live-merge-2026-06-02.json",
        {
            "kind": "live_cursor_worktree_merge",
            "status": "no_go",
            "finished_at": "2026-06-02T01:01:00+00:00",
            "preflight": {"ready": True},
        },
    )

    summary = discover_live_ops_reports(reports)

    assert summary["worktree"]["status"] == "skipped"
    assert summary["worktree"]["date"] == "2026-06-03"
    assert summary["worktree"]["file"] == "live-worktree-2026-06-03.json"
    assert summary["merge"]["status"] == "no_go"
    assert summary["merge"]["date"] == "2026-06-02"


def test_discover_live_ops_reports_empty_dir_is_na(tmp_path: Path):
    summary = discover_live_ops_reports(tmp_path / "missing")

    assert summary == {"worktree": None, "merge": None}


def test_weekly_report_markdown_surfaces_last_live_checks(tmp_path: Path):
    reports = tmp_path / "_reports"
    _write_json(
        reports / "live-worktree-2026-06-01.json",
        {
            "kind": "live_cursor_worktree_dry_run",
            "status": "go",
            "finished_at": "2026-06-01T02:00:00+00:00",
        },
    )
    _write_json(
        reports / "live-merge-2026-06-02.json",
        {
            "kind": "live_cursor_worktree_merge",
            "status": "no_go",
            "finished_at": "2026-06-02T02:00:00+00:00",
        },
    )

    report = build_weekly_report(
        REGRESSION.parent,
        days=30,
        include_fixtures=True,
        as_of=date(2026, 6, 3),
        report_dir=reports,
    )
    md = format_weekly_report_markdown(report)

    assert report["live_ops_summary"]["worktree"]["status"] == "go"
    assert report["live_ops_summary"]["merge"]["status"] == "no_go"
    assert any(
        "Last live: worktree GO (2026-06-01), merge NO_GO (2026-06-02)" in line for line in report["summary_lines"]
    )
    assert "## Last live checks" in md
    assert "| Tier B worktree | 2026-06-01 | GO | `live-worktree-2026-06-01.json` |" in md
    assert "| Tier C merge | 2026-06-02 | NO_GO | `live-merge-2026-06-02.json` |" in md


def test_weekly_report_markdown_surfaces_na_without_live_reports(tmp_path: Path):
    report = build_weekly_report(
        REGRESSION.parent,
        days=30,
        include_fixtures=True,
        as_of=date(2026, 6, 3),
        report_dir=tmp_path / "_reports",
    )
    md = format_weekly_report_markdown(report)

    assert report["live_ops_summary"] == {"worktree": None, "merge": None}
    assert "Last live: worktree n/a (n/a), merge n/a (n/a)" in "\n".join(report["summary_lines"])
    assert "| Tier B worktree | n/a | — | — |" in md
    assert "| Tier C merge | n/a | — | — |" in md
