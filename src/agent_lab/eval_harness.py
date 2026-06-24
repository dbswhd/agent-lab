"""SWE-bench-style eval harness scorer + model-vs-harness attribution (G5).

Pure stdlib, deterministic: no IO, no subprocess, no network. Default OFF via
AGENT_LAB_EVAL_HARNESS, and intentionally NOT wired into any existing module this
increment (zero call sites => OFF-parity is structurally guaranteed; existing
scoring/verification are byte-identical regardless of the flag).

``score_instance`` scores ONE benchmark instance from an already-parsed per-test
result map plus the instance's declared FAIL_TO_PASS / PASS_TO_PASS test ids and an
optional harness status. Parsing pytest/junit output into the result map is the
caller's job (out of scope). ``aggregate`` rolls a list of scorer results into a
model-vs-harness report whose resolved-rate denominator EXCLUDES harness failures,
so environment breakage never lowers the model's score.
"""

from __future__ import annotations

import os
from typing import Any, Literal

_TRUE = frozenset({"1", "true", "yes", "on"})

# Harness/env statuses that attribute a non-resolution to the harness, not the model.
HARNESS_STATUSES = frozenset({"setup_error", "collection_error", "timeout", "infra_error"})

Attribution = Literal["model", "harness"]

# A single scored instance.
ScoreResult = dict[str, Any]
# The aggregate model-vs-harness report.
AggregateReport = dict[str, Any]


def eval_harness_enabled() -> bool:
    """AGENT_LAB_EVAL_HARNESS (default ON). Opt-out via =0."""
    raw = os.getenv("AGENT_LAB_EVAL_HARNESS")
    if raw is None or raw.strip() == "":
        return True
    return raw.strip().lower() in _TRUE


def _bucket_counts(ids: list[str], result_map: dict[str, str]) -> tuple[int, int, bool]:
    """Return (passed, total, all_present). A present id passes iff its value == "pass"."""
    total = len(ids)
    passed = 0
    all_present = True
    for tid in ids:
        if tid not in result_map:
            all_present = False
            continue
        if result_map[tid] == "pass":
            passed += 1
    return passed, total, all_present


def score_instance(
    result_map: dict[str, str],
    f2p_ids: list[str],
    p2p_ids: list[str],
    status: str = "ok",
) -> ScoreResult:
    """Score one instance with a strict attribution precedence ladder.

    Precedence (harness always before model):
      1. status != "ok"                       -> harness (reason=status)
      2. any declared f2p/p2p id missing      -> harness (reason="missing_test_ids")
      3. all f2p pass AND all p2p pass        -> resolved, model (reason="resolved")
      4. otherwise                            -> unresolved, model
                                                 (reason="f2p_unfixed" | "p2p_regressed")

    Invariant: resolved=True implies attribution="model" (never harness). For a
    PRESENT declared id, any value != "pass" counts as not-passing; an ABSENT
    declared id triggers the missing_test_ids harness case.
    """
    f2p_passed, f2p_total, f2p_all_present = _bucket_counts(f2p_ids, result_map)
    p2p_passed, p2p_total, p2p_all_present = _bucket_counts(p2p_ids, result_map)

    def _result(resolved: bool, attribution: Attribution, reason: str) -> ScoreResult:
        return {
            "resolved": resolved,
            "attribution": attribution,
            "f2p_passed": f2p_passed,
            "f2p_total": f2p_total,
            "p2p_passed": p2p_passed,
            "p2p_total": p2p_total,
            "reason": reason,
        }

    # Step 1: harness status.
    if status != "ok":
        return _result(False, "harness", status)
    # Step 2: missing declared test ids.
    if not (f2p_all_present and p2p_all_present):
        return _result(False, "harness", "missing_test_ids")
    # Step 3: resolved (all present and all pass).
    f2p_ok = f2p_passed == f2p_total
    p2p_ok = p2p_passed == p2p_total
    if f2p_ok and p2p_ok:
        return _result(True, "model", "resolved")
    # Step 4: model failure.
    reason = "f2p_unfixed" if not f2p_ok else "p2p_regressed"
    return _result(False, "model", reason)


def aggregate(results: list[ScoreResult]) -> AggregateReport:
    """Roll scorer results into a model-vs-harness report.

    ``model_resolved_rate = resolved / (total - harness_failure_count)`` so harness
    failures are excluded from the denominator; the rate is 0.0 when the denominator
    is 0 (empty list or all-harness list). Pure and deterministic.
    """
    total = len(results)
    resolved = sum(1 for r in results if r.get("resolved"))
    harness_failure_count = sum(1 for r in results if r.get("attribution") == "harness")
    model_unresolved_count = sum(1 for r in results if r.get("attribution") == "model" and not r.get("resolved"))
    model_count = sum(1 for r in results if r.get("attribution") == "model")
    denom = total - harness_failure_count
    model_resolved_rate = (resolved / denom) if denom > 0 else 0.0
    return {
        "total": total,
        "resolved": resolved,
        "model_resolved_rate": model_resolved_rate,
        "harness_failure_count": harness_failure_count,
        "model_unresolved_count": model_unresolved_count,
        "by_attribution": {"model": model_count, "harness": harness_failure_count},
    }
