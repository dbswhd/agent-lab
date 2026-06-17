"""Verification lane report parsing."""

from __future__ import annotations

import json

from agent_lab.verification_report import (
    LANE_MARKER_EXPRESSIONS,
    build_verification_report,
    parse_collect_counts,
    update_verification_report,
)


def test_parse_collect_counts_from_deselected_summary() -> None:
    output = "1035/1420 tests collected (385 deselected) in 0.88s\n"

    counts = parse_collect_counts(output)

    assert counts == (1035, 1420)


def test_build_verification_report_defaults_to_not_run(tmp_path) -> None:
    report = build_verification_report(tmp_path)

    assert report["lanes"]["fast"]["status"] == "not_run"
    assert report["lanes"]["bridge"]["marker_expression"] == "bridge and not live"


def test_update_verification_report_writes_latest_and_lane_report(tmp_path) -> None:
    report = update_verification_report(
        sessions_dir=tmp_path,
        lane="fast",
        command=["pytest", "tests/", "-q"],
        marker_expression=LANE_MARKER_EXPRESSIONS["fast"],
        status="passed",
        exit_code=0,
        started_at="2026-06-17T00:00:00Z",
        finished_at="2026-06-17T00:00:01Z",
        duration_seconds=1.1,
        selected_count=10,
        total_count=12,
        failure_summary=None,
    )

    latest = tmp_path / "_reports" / "verification-latest.json"
    lane_report = tmp_path / "_reports" / "verification-fast-latest.json"

    assert latest.is_file()
    assert lane_report.is_file()
    assert report["lanes"]["fast"]["selected_count"] == 10
    assert json.loads(latest.read_text(encoding="utf-8"))["lanes"]["fast"]["status"] == "passed"
