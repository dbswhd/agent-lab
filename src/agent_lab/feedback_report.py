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
from collections import Counter
from pathlib import Path
from typing import Any

from agent_lab.correction_harvester import CORRECTION_PHASE
from agent_lab.feedback_advisor import MIN_SAMPLE, _score_outcome

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


def _is_verdict_eligible(row: dict[str, Any]) -> bool:
    """Only ``phase == "execute"`` rows carry a real Oracle verdict.

    ``turn``-phase and legacy (pre-phase-field) rows are written mid-discussion,
    before execute/verify has run — ``final_verdict`` is structurally always
    null on them (see ``outcome_harvester.record_execute_outcome`` docstring).
    Mixing them into clean-pass buckets pins the rate near zero regardless of
    real mission quality, so they're excluded from quality aggregation here.
    """
    return str(row.get("phase") or "") == "execute"


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


_LADDER_LEVELS = ("L0", "L1", "L2", "L3")


def _escalation_rate_by_level(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """Human Inbox reach rate per autonomy level (N4 KPI)."""
    buckets: dict[str, list[int]] = {level: [] for level in _LADDER_LEVELS}
    for row in rows:
        level = str(row.get("autonomy_level") or "L0")
        if level not in buckets:
            level = "L0"
        hit = 1 if row.get("human_inbox_escalation") else 0
        buckets[level].append(hit)
    out: dict[str, float | None] = {}
    for level in _LADDER_LEVELS:
        samples = buckets[level]
        out[level] = round(sum(samples) / len(samples), 4) if samples else None
    return out


def _correction_pattern_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """N10a — recurrence of user-correction patterns across distinct sessions.

    ``correction_recurrence_rate`` is the share of correction rows whose pattern
    has appeared in more than one distinct session (i.e. it recurred instead of
    being fixed after the first observation) — a downward-trending KPI.
    """
    correction_rows = [r for r in rows if str(r.get("phase") or "") == "user_correction"]
    by_pattern: dict[str, set[str]] = {}
    for row in correction_rows:
        key = str(row.get("pattern_key") or "")
        if not key:
            continue
        by_pattern.setdefault(key, set()).add(str(row.get("session_id") or ""))

    patterns = {
        key: {"n": sum(1 for r in correction_rows if r.get("pattern_key") == key), "sessions": len(sessions)}
        for key, sessions in by_pattern.items()
    }

    total = len(correction_rows)
    recurring = sum(1 for r in correction_rows if len(by_pattern.get(str(r.get("pattern_key") or ""), ())) > 1)
    rate = round(recurring / total, 4) if total else None

    return {
        "total": total,
        "by_pattern": patterns,
        "correction_recurrence_rate": rate,
    }


def build_feedback_report(root: Path | None = None) -> dict[str, Any]:
    """Bucket the outcome ledger by advisor_source and compute quality deltas.

    Returns a dict with overall counts, per-source stats, per-(source,category)
    stats, and an ``advisor_lift`` summary (history/explore clean-pass minus the
    default baseline). Empty ledger → ``{"total": 0, ...}`` with zeroed buckets.
    """
    all_rows = _load_rows(root)
    correction_stats = _correction_pattern_stats(all_rows)
    # N10a correction rows are a distinct Wisdom episode kind (user turn, not
    # agent turn/execute) — excluded here so they don't dilute S1 turn/execute
    # counts; they're reported separately via ``correction_patterns`` below.
    rows = [row for row in all_rows if str(row.get("phase") or "") != CORRECTION_PHASE]
    verdict_rows = [row for row in rows if _is_verdict_eligible(row)]
    by_source: dict[str, list[dict[str, Any]]] = {s: [] for s in _SOURCES}
    by_source_category: dict[str, dict[str, list[dict[str, Any]]]] = {s: {} for s in _SOURCES}

    for row in verdict_rows:
        src = _source_of(row)
        by_source[src].append(row)
        cat = str(row.get("category") or "")
        by_source_category[src].setdefault(cat, []).append(row)

    source_stats = {s: _bucket_stats(by_source[s]) for s in _SOURCES}
    source_category_stats = {s: {cat: _bucket_stats(rs) for cat, rs in by_source_category[s].items()} for s in _SOURCES}

    baseline_clean = source_stats[_BASELINE_SOURCE]["clean_pass_rate"]

    def _lift(source: str) -> float | None:
        """None below MIN_SAMPLE — an empty/near-empty bucket isn't a real signal
        (see NORTH-STAR §1 S1 관측 절차: n < MIN_SAMPLE means not yet "표본 충족")."""
        if source_stats[source]["n"] < MIN_SAMPLE:
            return None
        return round(source_stats[source]["clean_pass_rate"] - baseline_clean, 4)

    advisor_lift = {
        "history_vs_default": _lift("history"),
        "explore_vs_default": _lift("explore"),
    }

    total = len(rows)
    eligible = len(verdict_rows)
    turn_source_counts = Counter(_source_of(row) for row in rows)

    return {
        "total": total,
        "verdict_eligible_total": eligible,
        "turn_signal_total": total - eligible,
        "oracle_verdict_coverage": round(eligible / total, 4) if total else 0.0,
        "turn_source_counts": {source: turn_source_counts.get(source, 0) for source in _SOURCES},
        "by_source": source_stats,
        "by_source_category": source_category_stats,
        "advisor_lift": advisor_lift,
        "escalation_rate_by_level": _escalation_rate_by_level(rows),
        "correction_patterns": correction_stats,
    }


def render_feedback_report(report: dict[str, Any]) -> str:
    """Render a compact text table from ``build_feedback_report`` output."""
    lines: list[str] = []
    total = report.get("total", 0)
    eligible = report.get("verdict_eligible_total", total)
    turn_signal = report.get("turn_signal_total", total - eligible)
    coverage = report.get("oracle_verdict_coverage", 0.0)
    lines.append(f"S1.5 feedback effect report — {total} outcome rows ({eligible} execute-phase / verdict-eligible)")
    lines.append(f"  turn_signal_total: {turn_signal}  oracle_verdict_coverage: {coverage:.2%}")
    if "turn_source_counts" in report:
        lines.append(f"  turn_source_counts: {report['turn_source_counts']}")
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

    def _fmt_lift(value: float | None) -> str:
        return f"{value:+.2%}" if isinstance(value, float) else "— (below MIN_SAMPLE)"

    lines.append("advisor lift (clean-pass vs default baseline):")
    lines.append(f"  history : {_fmt_lift(lift.get('history_vs_default'))}")
    lines.append(f"  explore : {_fmt_lift(lift.get('explore_vs_default'))}")
    by_level = report.get("escalation_rate_by_level") or {}
    if by_level:
        lines.append("")
        lines.append("escalation_rate_by_level (human inbox):")
        for level in _LADDER_LEVELS:
            rate = by_level.get(level)
            label = f"{rate:.2%}" if isinstance(rate, float) else "—"
            lines.append(f"  {level}: {label}")
    correction = report.get("correction_patterns") or {}
    if correction.get("total"):
        rate = correction.get("correction_recurrence_rate")
        rate_label = f"{rate:.2%}" if isinstance(rate, float) else "—"
        lines.append("")
        lines.append(f"correction_patterns (N10a) — {correction['total']} rows, recurrence_rate: {rate_label}")
        for key, stats in sorted(correction.get("by_pattern", {}).items()):
            lines.append(f"  {key}: n={stats['n']} sessions={stats['sessions']}")
    return "\n".join(lines)
