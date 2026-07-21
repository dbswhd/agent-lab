"""S1.5 — feedback effect report: did the advisor actually help?

Reads the cross-session outcome ledger (``.agent-lab/outcomes.jsonl``) and
buckets rows by ``advisor_source`` ("default" | "history" | "explore") and
``category``, then reports per-bucket quality so the loop can be *validated*
(not just assumed). Pure read + aggregation; no I/O beyond loading the ledger.

Key questions this answers:
- Does the ``history`` (exploit) bucket beat the ``default`` baseline on
  clean-pass rate? → the advisor is picking better setups.
- Does ``explore`` surface combos worth promoting? → the seed is working.

See docs/archive/rfcs/DESIGN-S1-FEEDBACK-LOOP.md and the S1.5 plan.
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


def _tool_card_hit_stats(verdict_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """S3a-0 — did RECALL's tool-card suggestions correlate with clean-pass?

    ``tool_card_hit_rate`` is the clean-pass rate among execute-phase rows that
    carried a tool-card suggestion (an MVP proxy for "the suggestion helped" —
    it does not yet track whether the suggested tool was actually adopted,
    only whether a suggestion was present when the outcome landed).
    """
    suggested = [r for r in verdict_rows if r.get("tool_card_suggestions")]
    n = len(suggested)
    if n == 0:
        return {"n": 0, "tool_card_hit_rate": None}
    clean = sum(1 for r in suggested if _is_clean_pass(r))
    return {"n": n, "tool_card_hit_rate": round(clean / n, 4)}


def _harness_attribution_stats(verdict_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """HS0-2 — model-vs-harness attribution over execute-phase outcome rows.

    Oracle's ``verdict == "skipped"`` (plan action had no ``검증:`` criterion) is
    a harness-side gap, not a model failure — see
    ``eval_harness.score_outcome_verdict``. Rows with no verdict at all never
    reached Oracle and are excluded. ``None`` when AGENT_LAB_EVAL_HARNESS is off.
    """
    from agent_lab.eval_harness import aggregate, eval_harness_enabled, score_outcome_verdict

    if not eval_harness_enabled():
        return None
    scored = [score_outcome_verdict(str(r.get("final_verdict") or "")) for r in verdict_rows if r.get("final_verdict")]
    return aggregate(scored)


def _self_patch_stats(verdict_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """N6 — observation only: how often an execution stayed entirely inside the
    self-patch allowlist (see self_patch.py). No autonomy behavior reads this
    yet; it exists so a future decision has real data instead of a guess."""
    total = len(verdict_rows)
    if total == 0:
        return {"n": 0, "eligible_n": 0, "self_patch_eligible_rate": None}
    eligible = sum(1 for r in verdict_rows if (r.get("self_patch") or {}).get("eligible"))
    return {"n": total, "eligible_n": eligible, "self_patch_eligible_rate": round(eligible / total, 4)}


def _harness_patch_kpi(root: Path | None) -> dict[str, Any] | None:
    """HS5-5 — accept_rate / prediction_accuracy over the harness_patch pipeline
    (.agent-lab/harness/candidates + predictions.jsonl, not the outcome ledger).
    None when AGENT_LAB_HARNESS_INBOX is off."""
    from agent_lab.merge_gate import harness_inbox_enabled, harness_patch_stats

    if not harness_inbox_enabled():
        return None
    return harness_patch_stats(root)


def _harness_reproducibility_stats(root: Path | None) -> dict[str, Any] | None:
    """HS0-4 — latest scaffold (room preset fast/supervisor) reproducibility
    report from ``scripts/run_dogfood_suite.py --mode reproducibility``
    (sessions/_reports/dogfood-suite-reproducibility-*.json, not the outcome
    ledger). None when no such report has been generated yet."""
    from agent_lab.outcome_harvester import agent_lab_project_root

    reports_dir = agent_lab_project_root(root) / "sessions" / "_reports"
    if not reports_dir.is_dir():
        return None
    candidates = sorted(reports_dir.glob("dogfood-suite-reproducibility-*.json"))
    if not candidates:
        return None
    try:
        data = json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {
        "harness_reproducibility_pp": data.get("harness_reproducibility_pp"),
        "pass_rate_by_preset": data.get("pass_rate_by_preset"),
        "topics_compared": data.get("topics_compared"),
        "generated_at": data.get("generated_at"),
    }


def _stuck_discuss_sessions(root: Path | None, *, top_n: int = 10) -> list[dict[str, Any]]:
    """P2-2 — sessions parked in mission_loop DISCUSS/PLAN_GATE with
    mission_loop.enabled still False, ranked by agent-parallel rounds burned.

    Quantifies "converged in chat but never executed" (see the chat-Room
    execute-gate reachability investigation, 2026-07-21/22): a long tail here
    means the P0/P1 discoverability fixes (/execute, /plan execute, the
    round-1 consensus retry) aren't reaching real sessions yet. Reads
    ``sessions/*/run.json`` directly — this is per-session FSM state, not an
    outcome-ledger signal, so it can't be derived from ``outcomes.jsonl`` rows.
    """
    from agent_lab.outcome_harvester import agent_lab_project_root

    sessions_dir = agent_lab_project_root(root) / "sessions"
    if not sessions_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for folder in sorted(sessions_dir.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        run_path = folder / "run.json"
        if not run_path.is_file():
            continue
        try:
            run = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(run, dict):
            continue
        ml = run.get("mission_loop")
        if not isinstance(ml, dict):
            continue
        if ml.get("enabled") or str(ml.get("phase") or "") not in {"DISCUSS", "PLAN_GATE", "PLAN_REJECT"}:
            continue
        rows.append(
            {
                "session_id": folder.name,
                "topic": str(run.get("topic") or "")[:80],
                "rounds": int(run.get("agent_parallel_rounds") or 0),
                "phase": str(ml.get("phase") or ""),
            }
        )
    rows.sort(key=lambda r: (-r["rounds"], r["session_id"]))
    return rows[:top_n]


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
        "tool_cards": _tool_card_hit_stats(verdict_rows),
        "self_patch": _self_patch_stats(verdict_rows),
        "harness_attribution": _harness_attribution_stats(verdict_rows),
        "harness_patch": _harness_patch_kpi(root),
        "harness_reproducibility": _harness_reproducibility_stats(root),
        "stuck_discuss_sessions": _stuck_discuss_sessions(root),
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
    tool_cards = report.get("tool_cards") or {}
    if tool_cards.get("n"):
        hit_rate = tool_cards.get("tool_card_hit_rate")
        hit_label = f"{hit_rate:.2%}" if isinstance(hit_rate, float) else "—"
        lines.append("")
        lines.append(f"tool_cards (S3a-0) — {tool_cards['n']} suggested rows, hit_rate: {hit_label}")
    self_patch = report.get("self_patch") or {}
    if self_patch.get("n"):
        rate = self_patch.get("self_patch_eligible_rate")
        rate_label = f"{rate:.2%}" if isinstance(rate, float) else "—"
        lines.append("")
        lines.append(
            f"self_patch (N6) — {self_patch['eligible_n']}/{self_patch['n']} executions allowlist-eligible, rate: {rate_label}"
        )
    harness_attr = report.get("harness_attribution")
    if harness_attr and harness_attr.get("total"):
        lines.append("")
        lines.append(
            f"harness_attribution (HS0) — {harness_attr['total']} execute rows, "
            f"model_resolved_rate={harness_attr['model_resolved_rate']:.2%}, "
            f"harness_failure_rate={harness_attr['harness_failure_rate']:.2%} "
            f"({harness_attr['harness_failure_count']} harness failures)"
        )
    harness_patch = report.get("harness_patch")
    if harness_patch and harness_patch.get("candidates_decided"):
        accept = harness_patch.get("accept_rate")
        accept_label = f"{accept:.2%}" if isinstance(accept, float) else "—"
        acc = harness_patch.get("prediction_accuracy")
        acc_label = f"{acc:.2%}" if isinstance(acc, float) else "— (no verified predictions yet)"
        lines.append("")
        lines.append(
            f"harness_patch (HS5) — {harness_patch['candidates_merged']}/{harness_patch['candidates_decided']} "
            f"accepted (rate={accept_label}), prediction_accuracy={acc_label}"
        )
    reproducibility = report.get("harness_reproducibility")
    if reproducibility and reproducibility.get("harness_reproducibility_pp") is not None:
        lines.append("")
        lines.append(
            f"harness_reproducibility (HS0-4) — {reproducibility['topics_compared']} topics, "
            f"pp_deviation={reproducibility['harness_reproducibility_pp']} "
            f"pass_rate_by_preset={reproducibility['pass_rate_by_preset']}"
        )
    stuck = report.get("stuck_discuss_sessions") or []
    if stuck:
        lines.append("")
        lines.append(f"stuck_discuss_sessions (P2-2) — top {len(stuck)} by rounds burned, never executed:")
        for row in stuck:
            lines.append(f"  {row['rounds']:>3} rounds  [{row['phase']}]  {row['session_id']}  — {row['topic']}")
    return "\n".join(lines)
