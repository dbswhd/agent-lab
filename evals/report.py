from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal

from evals.graders import run_graders
from evals.mock_generation import generate_mock_session
from evals.schema import CaseResult, EvalCase, EvalReport, GraderResult, Supersample
from evals.trace_export import export_session_trace

ROOT = Path(__file__).resolve().parents[1]
REGRESSION_DIR = ROOT / "sessions" / "_regression"

QUICKSTART_COMMANDS = (
    "make quickstart-verify",
    "make emergence-bench-check",
    "make feedback-report JSON=1",
    "make dogfood-feedback-mock",
    "make eval-surface-local",
)

FORK_TIME_MINUTES_BASELINE = 12


def grade_case(case: EvalCase, *, regression_dir: Path, generated_dir: Path) -> CaseResult:
    case_id = case["case_id"]
    fixture = case.get("fixture_session")
    session_source: Literal["fixture", "generated_mock", "none"] = "fixture"

    if not fixture:
        if "mock_run" not in case:
            return {
                "case_id": case_id,
                "session_id": None,
                "session_source": "none",
                "status": "skipped",
                "pass": None,
                "reason": case.get("skip_reason") or "no_fixture_or_mock_run_mapped",
                "graders": [],
            }
        session_dir = generate_mock_session(case, generated_dir)
        session_source = "generated_mock"
    else:
        session_dir = regression_dir / fixture

    if not session_dir.is_dir():
        return {
            "case_id": case_id,
            "session_id": fixture,
            "session_source": session_source,
            "status": "error",
            "pass": False,
            "reason": f"fixture folder missing: {session_dir}",
            "graders": [],
        }

    trace = export_session_trace(session_dir, case_id=case_id)
    graders = coerce_grader_results(run_graders(trace, dict(case)))
    overall_pass = all(g["pass"] for g in graders) if graders else True

    return {
        "case_id": case_id,
        "session_id": str(trace["session_id"]),
        "session_source": session_source,
        "status": "graded",
        "pass": overall_pass,
        "reason": "" if overall_pass else "; ".join(g["reason"] for g in graders if not g["pass"] and g["reason"]),
        "graders": graders,
    }


def coerce_grader_results(raw: object) -> list[GraderResult]:
    results: list[GraderResult] = []
    if not isinstance(raw, list):
        return results
    for item in raw:
        if not isinstance(item, dict):
            continue
        grader = item.get("grader")
        case_id = item.get("case_id")
        session_id = item.get("session_id")
        passed = item.get("pass")
        score = item.get("score")
        reason = item.get("reason")
        evidence_raw = item.get("evidence")
        if (
            isinstance(grader, str)
            and isinstance(case_id, str)
            and isinstance(session_id, str)
            and isinstance(passed, bool)
            and isinstance(score, int | float)
            and isinstance(reason, str)
        ):
            evidence = [str(entry) for entry in evidence_raw] if isinstance(evidence_raw, list) else []
            results.append(
                {
                    "grader": grader,
                    "case_id": case_id,
                    "session_id": session_id,
                    "pass": passed,
                    "score": float(score),
                    "reason": reason,
                    "evidence": evidence,
                }
            )
    return results


def build_report(cases: list[EvalCase], *, regression_dir: Path = REGRESSION_DIR) -> EvalReport:
    with tempfile.TemporaryDirectory(prefix="eval-surface-generated-") as generated_root:
        generated_dir = Path(generated_root)
        case_results = [grade_case(case, regression_dir=regression_dir, generated_dir=generated_dir) for case in cases]
    failed = [c["case_id"] for c in case_results if c["status"] in ("graded", "error") and not c["pass"]]
    skipped = [c["case_id"] for c in case_results if c["status"] == "skipped"]

    return {
        "cases": case_results,
        "summary": {
            "total": len(case_results),
            "graded": sum(1 for c in case_results if c["status"] == "graded"),
            "skipped": len(skipped),
            "failed": failed,
            "skipped_case_ids": skipped,
        },
        "supersample": build_supersample(case_results),
    }


def build_supersample(case_results: list[CaseResult]) -> Supersample:
    graded = [c for c in case_results if c["status"] == "graded"]
    all_graders = [g for c in graded for g in c["graders"]]

    def by_grader(name: str) -> list[GraderResult]:
        return [g for g in all_graders if g["grader"] == name]

    routing = by_grader("routing_contract")
    gate = by_grader("gate_integrity")
    objection = by_grader("objection_flow")
    oracle = by_grader("oracle_coverage")
    completeness = by_grader("trace_completeness")
    s_quality = [
        g
        for c in graded
        if c["case_id"].startswith("S")
        for g in c["graders"]
        if g["grader"] == "generated_mock_quality"
    ]
    trace_rate = round(sum(g["score"] for g in completeness) / len(completeness), 4) if completeness else None

    return {
        "t0": {
            "routing_pass_rate": rate([g["pass"] for g in routing]),
            "human_gate_bypass_count": sum(1 for g in gate if not g["pass"]),
            "oracle_verdict_coverage": (round(sum(g["score"] for g in oracle) / len(oracle), 4) if oracle else None),
            "trace_completeness_rate": trace_rate,
            "trace_completeness_interpretation": trace_completeness_interpretation(trace_rate),
            "objection_flow_pass_rate": rate([g["pass"] for g in objection]),
            "s_case_quality_pass_rate": rate([g["pass"] for g in s_quality]),
            "s_case_quality_failed": [g["case_id"] for g in s_quality if not g["pass"]],
        },
        "t1": {
            "quickstart_commands": list(QUICKSTART_COMMANDS),
            "expected_report_shape": "evals/results/latest.json#supersample",
            "fork_time_minutes": FORK_TIME_MINUTES_BASELINE,
        },
        "t2": {
            "external_fork_count": None,
            "external_issue_count": None,
            "external_pr_count": None,
            "gate": False,
        },
    }


def rate(values: list[bool]) -> float | None:
    return round(sum(1 for v in values if v) / len(values), 4) if values else None


def trace_completeness_interpretation(value: float | None) -> str:
    if value is None:
        return "not_measured"
    if value >= 0.8:
        return "strong_trace_coverage"
    if value >= 0.33:
        return "partial_coverage_expected_for_legacy_regression_fixtures"
    return "weak_trace_coverage_check_missing_spans"
