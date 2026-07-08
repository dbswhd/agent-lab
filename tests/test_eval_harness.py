"""P4 SWE-bench-style eval harness (AGENT_LAB_EVAL_HARNESS, default on).

Covers AC1-AC18 + Critic N1 (reason determinism) + N2 (allowlisted-importer scan).
The module is pure; HS0 wires it through ``feedback_report.py`` (harness_attribution)
and ``scripts/run_dogfood_suite.py`` (mock suite report) — see those modules.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab import eval_harness as eh


# --- scorer (single instance) ----------------------------------------------


def test_ac1_all_pass_resolved_model():
    r = eh.score_instance({"t1": "pass", "t2": "pass"}, ["t1"], ["t2"])
    assert r["resolved"] is True
    assert r["attribution"] == "model"
    assert r["reason"] == "resolved"


def test_ac2_clean_unfixed_f2p_unresolved_model():
    r = eh.score_instance({"t1": "fail", "t2": "pass"}, ["t1"], ["t2"])
    assert r["resolved"] is False
    assert r["attribution"] == "model"
    assert r["reason"] == "f2p_unfixed"


def test_ac3_missing_id_harness():
    r = eh.score_instance({"t2": "pass"}, ["t1"], ["t2"])  # t1 absent
    assert r["resolved"] is False
    assert r["attribution"] == "harness"
    assert r["reason"] == "missing_test_ids"


def test_ac4_bad_status_harness():
    for status in eh.HARNESS_STATUSES:
        r = eh.score_instance({"t1": "pass"}, ["t1"], [], status=status)
        assert r["resolved"] is False
        assert r["attribution"] == "harness"
        assert r["reason"] == status


def test_ac5_bucket_counts_exact():
    r = eh.score_instance(
        {"a": "pass", "b": "fail", "c": "pass", "d": "pass"},
        ["a", "b"],
        ["c", "d"],
    )
    assert (r["f2p_passed"], r["f2p_total"]) == (1, 2)
    assert (r["p2p_passed"], r["p2p_total"]) == (2, 2)


def test_ac6_p2p_regression_unresolved_model():
    r = eh.score_instance({"t1": "pass", "t2": "fail"}, ["t1"], ["t2"])
    assert r["resolved"] is False
    assert r["attribution"] == "model"
    assert r["reason"] == "p2p_regressed"


def test_ac7_scorer_pure_deterministic():
    args = ({"t1": "pass"}, ["t1"], [])
    assert eh.score_instance(*args) == eh.score_instance(*args)


# --- precedence ladder (Architect HIGH) ------------------------------------


def test_ac15_status_beats_model_failure():
    # timeout AND an unfixed F2P -> harness wins (not charged to model)
    r = eh.score_instance({"t1": "fail"}, ["t1"], [], status="timeout")
    assert r["attribution"] == "harness"
    assert r["reason"] == "timeout"


def test_ac16_missing_id_beats_p2p_regression():
    # t1 (f2p) missing AND t2 (p2p) regressed -> harness/missing wins
    r = eh.score_instance({"t2": "fail"}, ["t1"], ["t2"])
    assert r["attribution"] == "harness"
    assert r["reason"] == "missing_test_ids"


def test_ac18_non_pass_value_and_empty_f2p():
    # "error" value (present) counts as not-pass -> model unfixed
    r = eh.score_instance({"t1": "error"}, ["t1"], [])
    assert r["resolved"] is False
    assert r["attribution"] == "model"
    # empty f2p + all p2p pass + ok -> resolved
    r2 = eh.score_instance({"p": "pass"}, [], ["p"])
    assert r2["resolved"] is True
    assert r2["attribution"] == "model"


# --- aggregate -------------------------------------------------------------


def _mk(resolved: bool, attribution: str) -> dict:
    return {
        "resolved": resolved,
        "attribution": attribution,
        "f2p_passed": 0,
        "f2p_total": 0,
        "p2p_passed": 0,
        "p2p_total": 0,
        "reason": "x",
    }


def test_ac8_ac9_aggregate_shape_and_excluded_denominator():
    # 2 resolved(model), 1 unresolved(model), 1 harness -> rate = 2/(4-1) = 0.666...
    results = [
        _mk(True, "model"),
        _mk(True, "model"),
        _mk(False, "model"),
        _mk(False, "harness"),
    ]
    agg = eh.aggregate(results)
    assert agg["total"] == 4
    assert agg["resolved"] == 2
    assert agg["harness_failure_count"] == 1
    assert agg["model_unresolved_count"] == 1
    assert agg["by_attribution"] == {"model": 3, "harness": 1}
    assert abs(agg["model_resolved_rate"] - (2 / 3)) < 1e-9


def test_ac10_empty_list():
    agg = eh.aggregate([])
    assert agg["total"] == 0
    assert agg["resolved"] == 0
    assert agg["model_resolved_rate"] == 0.0
    assert agg["harness_failure_rate"] == 0.0


def test_harness_failure_rate_over_total():
    # HS0-3: harness_failure_rate divides by total (unlike model_resolved_rate,
    # which excludes harness failures from its denominator).
    agg = eh.aggregate([_mk(True, "model"), _mk(False, "model"), _mk(False, "harness")])
    assert agg["harness_failure_rate"] == pytest.approx(1 / 3)


def test_ac11_all_harness():
    agg = eh.aggregate([_mk(False, "harness"), _mk(False, "harness")])
    assert agg["harness_failure_count"] == 2
    assert agg["model_resolved_rate"] == 0.0  # denominator 0 guarded


def test_ac12_aggregate_pure():
    results = [_mk(True, "model"), _mk(False, "harness")]
    assert eh.aggregate(results) == eh.aggregate(results)


def test_ac17_rate_in_unit_interval_and_resolved_implies_model():
    # Build a mixed list via score_instance ONLY (invariant: resolved => model)
    produced = [
        eh.score_instance({"t": "pass"}, ["t"], []),  # resolved model
        eh.score_instance({"t": "fail"}, ["t"], []),  # unresolved model
        eh.score_instance({"t": "pass"}, ["t"], [], status="timeout"),  # harness
        eh.score_instance({}, ["t"], []),  # missing -> harness
    ]
    # No score_instance output is ever resolved+harness
    for r in produced:
        if r["resolved"]:
            assert r["attribution"] == "model"
    agg = eh.aggregate(produced)
    assert 0.0 <= agg["model_resolved_rate"] <= 1.0


# --- HS0 adapters -----------------------------------------------------------


def test_score_dogfood_status_error_is_harness():
    r = eh.score_dogfood_status("error")
    assert r == {"resolved": False, "attribution": "harness", "reason": "dogfood_error"}


def test_score_dogfood_status_pass_and_ran_resolve_model():
    for status in ("pass", "ran"):
        r = eh.score_dogfood_status(status)
        assert r["resolved"] is True
        assert r["attribution"] == "model"


def test_score_dogfood_status_fail_is_unresolved_model():
    r = eh.score_dogfood_status("fail")
    assert r["resolved"] is False
    assert r["attribution"] == "model"
    assert r["reason"] == "dogfood_fail"


def test_score_dogfood_status_aggregate_end_to_end():
    statuses = ["pass", "pass", "fail", "error"]
    agg = eh.aggregate([eh.score_dogfood_status(s) for s in statuses])
    assert agg["total"] == 4
    assert agg["harness_failure_count"] == 1
    assert agg["model_resolved_rate"] == pytest.approx(2 / 3)  # 2 resolved / (4-1) model rows


def test_score_outcome_verdict_skipped_is_harness_missing_criterion():
    r = eh.score_outcome_verdict("skipped")
    assert r == {"resolved": False, "attribution": "harness", "reason": "missing_verify_criterion"}


def test_score_outcome_verdict_pass_resolves_model():
    r = eh.score_outcome_verdict("pass")
    assert r["resolved"] is True
    assert r["attribution"] == "model"


def test_score_outcome_verdict_fail_is_unresolved_model():
    r = eh.score_outcome_verdict("fail")
    assert r["resolved"] is False
    assert r["attribution"] == "model"


# --- flag + OFF-parity -----------------------------------------------------


def test_ac13_flag_default_on(monkeypatch):
    # default ON: absent/empty => enabled; opt-out via =0
    monkeypatch.delenv("AGENT_LAB_EVAL_HARNESS", raising=False)
    assert eh.eval_harness_enabled() is True
    monkeypatch.setenv("AGENT_LAB_EVAL_HARNESS", "0")
    assert eh.eval_harness_enabled() is False
    monkeypatch.setenv("AGENT_LAB_EVAL_HARNESS", "1")
    assert eh.eval_harness_enabled() is True


def test_ac13_n2_wired_through_ingest_only():
    # HS0-2 wires ``feedback_report.py`` to eval_harness (harness_attribution over
    # the outcome ledger) — a designated integration point, not an accidental import.
    # This guard now enforces "only these named modules", not "zero call sites".
    src = Path(__file__).resolve().parent.parent / "src" / "agent_lab"
    allowed = {"eval_harness.py", "eval_harness_ingest.py", "feedback_report.py"}
    offenders = []
    for py in src.glob("*.py"):
        if py.name in allowed:
            continue
        text = py.read_text(encoding="utf-8")
        if "eval_harness" in text:
            offenders.append(py.name)
    assert offenders == [], f"unexpected eval_harness importers: {offenders}"
    ingest = (src / "eval_harness_ingest.py").read_text(encoding="utf-8")
    assert "score_instance" in ingest


def test_n1_reason_strings_deterministic():
    a = eh.score_instance({"t": "fail"}, ["t"], [])
    b = eh.score_instance({"t": "fail"}, ["t"], [])
    assert a["reason"] == b["reason"] == "f2p_unfixed"
