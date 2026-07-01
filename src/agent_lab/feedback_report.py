"""S1.5 — feedback effect report: did the advisor actually help?

Reads the cross-session outcome ledger (``.agent-lab/outcomes.jsonl``) and
buckets rows by ``advisor_source`` ("default" | "history" | "explore") and
``category``, then reports per-bucket quality so the loop can be *validated*
(not just assumed). Pure read + aggregation; no I/O beyond loading the ledger.

Key questions this answers:
- Does the ``history`` (exploit) bucket beat the ``default`` baseline on
  clean-pass rate? → the advisor is picking better setups.
- Does ``explore`` surface combos worth promoting? → the seed is working.

See docs/DESIGN-S1-FEEDBACK-LOOP.md and the S1.5 plan.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_lab.feedback_advisor import _score_outcome

# Rows written before S1.5 (no advisor_source) fold into this baseline bucket.
_BASELINE_SOURCE = "default"
_SOURCES = ("default", "history", "explore")


def _load_rows(root: Path | None) -> list[dict[str, Any]]:
    from agent_lab.outcome_harvester import outcomes_path

    path = outcomes_path(root)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _is_clean_pass(row: dict[str, Any]) -> bool:
    return str(row.get("final_verdict") or "").lower() == "pass" and int(row.get("repair_attempts") or 0) == 0


def _blocks(row: dict[str, Any]) -> int:
    return int((row.get("objection_summary") or {}).get("BLOCK", 0))


def _accepted_challenges(row: dict[str, Any]) -> int:
    res = (row.get("objection_resolution") or {}).get("CHALLENGE") or {}
    return int(res.get("accepted") or 0)


def _bucket_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate quality signals for one bucket of outcome rows."""
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "clean_pass_rate": 0.0,
            "repair_rate": 0.0,
            "block_rate": 0.0,
            "accepted_challenge_rate": 0.0,
            "avg_score": 0.0,
        }
    clean = sum(1 for r in rows if _is_clean_pass(r))
    repaired = sum(1 for r in rows if int(r.get("repair_attempts") or 0) > 0)
    blocked = sum(1 for r in rows if _blocks(r) > 0)
    challenged = sum(1 for r in rows if _accepted_challenges(r) > 0)
    total_score = sum(_score_outcome(r) for r in rows)
    return {
        "n": n,
        "clean_pass_rate": round(clean / n, 4),
        "repair_rate": round(repaired / n, 4),
        "block_rate": round(blocked / n, 4),
        "accepted_challenge_rate": round(challenged / n, 4),
        "avg_score": round(total_score / n, 4),
    }


def _source_of(row: dict[str, Any]) -> str:
    src = str(row.get("advisor_source") or _BASELINE_SOURCE)
    return src if src in _SOURCES else _BASELINE_SOURCE


def build_feedback_report(root: Path | None = None) -> dict[str, Any]:
    """Bucket the outcome ledger by advisor_source and compute quality deltas.

    Returns a dict with overall counts, per-source stats, per-(source,category)
    stats, and an ``advisor_lift`` summary (history/explore clean-pass minus the
    default baseline). Empty ledger → ``{"total": 0, ...}`` with zeroed buckets.
    """
    rows = _load_rows(root)
    by_source: dict[str, list[dict[str, Any]]] = {s: [] for s in _SOURCES}
    by_source_category: dict[str, dict[str, list[dict[str, Any]]]] = {s: {} for s in _SOURCES}

    for row in rows:
        src = _source_of(row)
        by_source[src].append(row)
        cat = str(row.get("category") or "")
        by_source_category[src].setdefault(cat, []).append(row)

    source_stats = {s: _bucket_stats(by_source[s]) for s in _SOURCES}
    source_category_stats = {
        s: {cat: _bucket_stats(rs) for cat, rs in by_source_category[s].items()} for s in _SOURCES
    }

    baseline_clean = source_stats[_BASELINE_SOURCE]["clean_pass_rate"]
    advisor_lift = {
        "history_vs_default": round(source_stats["history"]["clean_pass_rate"] - baseline_clean, 4),
        "explore_vs_default": round(source_stats["explore"]["clean_pass_rate"] - baseline_clean, 4),
    }

    return {
        "total": len(rows),
        "by_source": source_stats,
        "by_source_category": source_category_stats,
        "advisor_lift": advisor_lift,
    }


def render_feedback_report(report: dict[str, Any]) -> str:
    """Render a compact text table from ``build_feedback_report`` output."""
    lines: list[str] = []
    total = report.get("total", 0)
    lines.append(f"S1.5 feedback effect report — {total} outcome rows")
    lines.append("")
    lines.append(f"{'source':<10}{'n':>6}{'clean_pass':>12}{'repair':>9}{'block':>8}{'avg_score':>11}")
    lines.append("-" * 56)
    for src in _SOURCES:
        st = report["by_source"][src]
        lines.append(
            f"{src:<10}{st['n']:>6}{st['clean_pass_rate']:>12.2%}"
            f"{st['repair_rate']:>9.2%}{st['block_rate']:>8.2%}{st['avg_score']:>11.2f}"
        )
    lines.append("")
    lift = report.get("advisor_lift", {})
    lines.append("advisor lift (clean-pass vs default baseline):")
    lines.append(f"  history : {lift.get('history_vs_default', 0.0):+.2%}")
    lines.append(f"  explore : {lift.get('explore_vs_default', 0.0):+.2%}")
    return "\n".join(lines)
