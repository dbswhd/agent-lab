"""Eval Surface v1 — run_local integration tests against real sessions/_regression fixtures.

Fixture/mock-safe only: reads existing committed session folders, never runs a
live agent. See docs/EVAL-SURFACE-V1-PLAN.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from evals.run_local import REGRESSION_DIR, build_report, load_cases
from evals.schema import EvalCase

_CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "cases.jsonl"


def test_v1_cases_load_and_all_ten_are_present() -> None:
    cases = load_cases(_CASES_PATH)
    assert {c["case_id"] for c in cases} == {"S1", "S2", "S3", "M3", "M4", "M5", "L1", "L2", "L3", "X2"}


def test_build_report_against_real_fixtures_all_pass() -> None:
    cases = load_cases(_CASES_PATH)
    report = build_report(cases, regression_dir=REGRESSION_DIR)
    assert report["summary"]["failed"] == []
    assert report["summary"]["total"] == 10
    assert report["summary"]["skipped"] == 0
    assert report["summary"]["graded"] == 10


def test_generated_cases_are_graded_not_skipped() -> None:
    cases = load_cases(_CASES_PATH)
    report = build_report(cases, regression_dir=REGRESSION_DIR)
    generated = {c["case_id"]: c for c in report["cases"] if c["session_source"] == "generated_mock"}
    assert set(generated) == {"S1", "S2", "S3"}
    for result in generated.values():
        assert result["status"] == "graded"
        assert result["pass"] is True
        assert result["session_id"]


def test_generated_cases_enforce_routing_session_and_quality_contracts() -> None:
    cases = load_cases(_CASES_PATH)
    report = build_report(cases, regression_dir=REGRESSION_DIR)
    generated = {c["case_id"]: c for c in report["cases"] if c["session_source"] == "generated_mock"}
    for result in generated.values():
        grader_names = {g["grader"] for g in result["graders"]}
        assert "routing_contract" in grader_names
        assert "session_contract" in grader_names
        assert "generated_mock_quality" in grader_names


def test_generated_cases_have_richer_trace_completeness() -> None:
    cases = load_cases(_CASES_PATH)
    report = build_report(cases, regression_dir=REGRESSION_DIR)
    generated = {c["case_id"]: c for c in report["cases"] if c["session_source"] == "generated_mock"}
    for result in generated.values():
        trace_scores = [g["score"] for g in result["graders"] if g["grader"] == "trace_completeness"]
        assert trace_scores
        assert trace_scores[0] >= 0.85


def test_m3_block_gates_execute() -> None:
    cases = [c for c in load_cases(_CASES_PATH) if c["case_id"] == "M3"]
    report = build_report(cases, regression_dir=REGRESSION_DIR)
    case = report["cases"][0]
    assert case["status"] == "graded"
    assert case["pass"] is True
    grader_names = {g["grader"] for g in case["graders"]}
    assert "gate_integrity" in grader_names
    assert "objection_flow" in grader_names


def test_missing_fixture_folder_reports_error_not_crash(tmp_path: Path) -> None:
    cases: list[EvalCase] = [{"case_id": "GHOST", "fixture_session": "does_not_exist", "expected": {}, "forbidden": []}]
    report = build_report(cases, regression_dir=tmp_path)
    case = report["cases"][0]
    assert case["status"] == "error"
    assert case["pass"] is False
    assert "does_not_exist" in case["reason"]


def test_supersample_section_shape() -> None:
    cases = load_cases(_CASES_PATH)
    report = build_report(cases, regression_dir=REGRESSION_DIR)
    supersample = report["supersample"]
    assert set(supersample) == {"t0", "t1", "t2"}
    assert supersample["t0"]["routing_pass_rate"] == 1.0
    assert supersample["t0"]["human_gate_bypass_count"] == 0
    assert supersample["t0"]["trace_completeness_interpretation"]
    assert supersample["t0"]["s_case_quality_pass_rate"] == 1.0
    assert supersample["t0"]["s_case_quality_failed"] == []
    assert supersample["t1"]["fork_time_minutes"] == 12  # docs/REPRODUCTION-REPORT.md baseline
    assert supersample["t2"]["gate"] is False
    assert supersample["t2"]["external_fork_count"] is None


def test_discuss_only_and_execute_path_trace_profiles_score_as_expected() -> None:
    cases = load_cases(_CASES_PATH)
    report = build_report(cases, regression_dir=REGRESSION_DIR)
    by_case = {c["case_id"]: c for c in report["cases"]}

    def trace_score(case_id: str) -> float:
        case = by_case[case_id]
        for grader in case["graders"]:
            if grader["grader"] == "trace_completeness":
                return grader["score"]
        raise AssertionError(f"trace_completeness missing for {case_id}")

    assert trace_score("M4") == 1.0
    assert trace_score("L1") == 1.0
    assert trace_score("L2") == 1.0


def test_cli_writes_json_report(tmp_path: Path) -> None:
    import subprocess
    import sys

    out_path = tmp_path / "latest.json"
    result = subprocess.run(
        [sys.executable, "-m", "evals.run_local", "--cases", str(_CASES_PATH), "--out", str(out_path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["summary"]["failed"] == []
