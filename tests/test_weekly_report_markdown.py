"""Markdown artifact rendering for weekly KPI ops reports."""

from __future__ import annotations

from pathlib import Path

from agent_lab.session_score_weekly import (
    format_weekly_report_markdown,
    weekly_report_artifact_paths,
)


def test_format_weekly_report_markdown_surfaces_m4_and_f_r3():
    report = {
        "period": {"start": "2026-05-28", "end": "2026-06-03", "days": 7},
        "sessions_dir": "/tmp/sessions",
        "include_fixtures": True,
        "sessions": [
            {
                "session_id": "specialist_asymmetric_cwd",
                "scores": {
                    "objection_resolution_rate": None,
                    "execute_retry_rate": None,
                    "asymmetric_capability_cwd": 1.0,
                    "specialist_context_recorded": 1.0,
                },
            }
        ],
        "aggregate": {
            "scores": {
                "specialist_context_recorded_rate": 1.0,
                "asymmetric_capability_cwd_rate": 0.5,
            },
            "counts": {
                "capability_cwd": {
                    "recorded": 2,
                    "asymmetric": 1,
                    "specialist_contexts": 2,
                }
            },
        },
        "m4_milestones": {
            "objection_resolution": {
                "value": 0.25,
                "target": ">=80%",
                "pass": False,
                "applicable": True,
            },
            "execute_retry": {
                "value": 0.1,
                "target": "<30%",
                "pass": True,
                "applicable": True,
            },
            "applicable_count": 2,
            "overall_pass": False,
        },
        "errors": ["bad-session: run.json missing"],
    }

    md = format_weekly_report_markdown(report)

    assert "# Agent Lab Weekly Ops Report" in md
    assert "## M4 Milestones" in md
    assert "| Objection resolution | 25% | >=80% | FAIL |" in md
    assert "| Execute retry | 10% | <30% | PASS |" in md
    assert "## F-R3 Ops" in md
    assert "| Capability cwd asymmetry | 50% | 1/2 contexts |" in md
    assert "`specialist_asymmetric_cwd`" in md
    assert "bad-session: run.json missing" in md


def test_weekly_report_artifact_paths():
    paths = weekly_report_artifact_paths("2026-06-03", Path("/tmp/reports"))

    assert paths["json"] == Path("/tmp/reports/weekly-2026-06-03.json")
    assert paths["md"] == Path("/tmp/reports/weekly-2026-06-03.md")
