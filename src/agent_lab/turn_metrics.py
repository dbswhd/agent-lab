"""S1 Phase A — turn_metrics: persistable per-turn outcome summary.

Pure functions that roll up an already-persisted turn snapshot plus run-level
objections/executions into a compact ``turn_metrics`` dict. No I/O here; the
``outcome_harvester`` module persists the result.

See docs/DESIGN-S1-FEEDBACK-LOOP.md (Phase A).
"""

from __future__ import annotations

from typing import Any

TURN_METRICS_SCHEMA_VERSION = 1

_RESOLUTION_BUCKETS = ("accepted", "wontfix", "open")

# HS1-1 failure taxonomy (docs/DESIGN-HARNESS-SELF-IMPROVE.md §8.1). Priority order
# doubles as primary_tag precedence (first match wins, mirrors HS0's scorer's
# harness-before-model ladder). Only tags with a reliable signal already available
# to this function are derived here; `stale_defaults`/`implementation_drift`/
# `context_loss`/`wrong_question` need instrumentation this increment doesn't add
# (raw error text, plan/diff comparison, drift_audit wiring) and are left for a
# follow-up HS1 pass rather than faked with unreliable heuristics.
_TAG_PRIORITY = ("harness_infra", "weak_taste", "false_success")


def _derive_failure_tags(
    *,
    objection_summary: dict[str, int],
    objection_resolution: dict[str, dict[str, int]],
    executions: list[dict[str, Any]],
) -> tuple[list[str], str | None]:
    """Best-effort HS1-1 failure tags from signals already computed this turn.

    ``harness_infra``: an execution's Oracle verdict is "skipped" (no ``검증:``
    criterion declared — see ``plan.execute_merge.oracle_verify``), same signal
    ``score_outcome_verdict`` (HS0's model-vs-harness scorer) uses for attribution.
    ``false_success``: an execution passed with no cited evidence (Oracle said
    pass but pointed at nothing).
    ``weak_taste``: an unresolved BLOCK, or CHALLENGE raised more than once this
    turn (repeated pushback the agents didn't converge on).
    """
    tags: set[str] = set()
    for execution in executions:
        if not isinstance(execution, dict):
            continue
        oracle = execution.get("oracle") if isinstance(execution.get("oracle"), dict) else {}
        verdict = str(oracle.get("verdict") or "").strip().lower()
        if verdict == "skipped":
            tags.add("harness_infra")
        elif verdict == "pass" and not oracle.get("evidence"):
            tags.add("false_success")
    block = objection_resolution.get("BLOCK") or {}
    if block.get("open", 0) > 0 or objection_summary.get("CHALLENGE", 0) >= 2:
        tags.add("weak_taste")
    ordered = [tag for tag in _TAG_PRIORITY if tag in tags]
    return ordered, (ordered[0] if ordered else None)


def _objection_summary(objections: list[dict[str, Any]], *, human_turn: int) -> dict[str, int]:
    """Count objection acts (CHALLENGE/BLOCK/AMEND/...) raised on this human turn."""
    summary: dict[str, int] = {}
    for obj in objections:
        if not isinstance(obj, dict):
            continue
        try:
            if int(obj.get("turn") or 0) != human_turn:
                continue
        except (TypeError, ValueError):
            continue
        act = str(obj.get("act") or "").strip().upper()
        if not act:
            continue
        summary[act] = summary.get(act, 0) + 1
    return summary


def _objection_resolution_summary(objections: list[dict[str, Any]], *, human_turn: int) -> dict[str, dict[str, int]]:
    """Per-act resolution counts for objections raised on this human turn."""
    summary: dict[str, dict[str, int]] = {}
    for obj in objections:
        if not isinstance(obj, dict):
            continue
        try:
            if int(obj.get("turn") or 0) != human_turn:
                continue
        except (TypeError, ValueError):
            continue
        act = str(obj.get("act") or "").strip().upper()
        if act not in {"CHALLENGE", "BLOCK"}:
            continue
        status = str(obj.get("status") or "open").strip().lower()
        bucket = "accepted" if status == "resolved_accepted" else "wontfix" if status == "resolved_wontfix" else "open"
        if bucket not in _RESOLUTION_BUCKETS:
            bucket = "open"
        act_counts = summary.setdefault(act, {k: 0 for k in _RESOLUTION_BUCKETS})
        act_counts[bucket] = act_counts.get(bucket, 0) + 1
    return summary


def _oracle_rollup(executions: list[dict[str, Any]]) -> dict[str, Any]:
    """Snapshot of the session's verification state at turn end.

    Executions accumulate across a session; Phase A attributes the current
    aggregate (pass/fail counts, repair attempts, last verdict) to the turn.
    """
    verify_pass = 0
    verify_fail = 0
    repair_attempts = 0
    final_verdict: str | None = None
    for execution in executions:
        if not isinstance(execution, dict):
            continue
        oracle = execution.get("oracle") if isinstance(execution.get("oracle"), dict) else {}
        verdict = str(oracle.get("verdict") or "").strip().lower()
        if not verdict:
            status = str((execution.get("verify_after_merge") or {}).get("status") or "").strip().lower()
            verdict = {"passed": "pass", "failed": "fail"}.get(status, "")
        if verdict == "pass":
            verify_pass += 1
            final_verdict = "pass"
        elif verdict == "fail":
            verify_fail += 1
            final_verdict = "fail"
        repair_attempts += len(execution.get("repair_history") or [])
    return {
        "verify_pass": verify_pass,
        "verify_fail": verify_fail,
        "repair_attempts": repair_attempts,
        "final_verdict": final_verdict,
    }


def build_turn_metrics(
    turn: dict[str, Any],
    *,
    objections: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    human_turn: int,
) -> dict[str, Any]:
    """Roll a persisted turn snapshot + run-level signals into turn_metrics.

    Inputs are all already-persisted values (no agent calls). ``turn`` is the
    snapshot produced by ``_turn_snapshot`` (typically ``run["turns"][-1]``).
    """
    category = turn.get("category") if isinstance(turn.get("category"), dict) else {}
    roles = turn.get("roles") if isinstance(turn.get("roles"), dict) else {}
    consensus = turn.get("consensus") if isinstance(turn.get("consensus"), dict) else {}

    objection_summary = _objection_summary(objections, human_turn=human_turn)
    objection_resolution = _objection_resolution_summary(objections, human_turn=human_turn)
    failure_tags, primary_tag = _derive_failure_tags(
        objection_summary=objection_summary,
        objection_resolution=objection_resolution,
        executions=executions,
    )

    metrics: dict[str, Any] = {
        "schema_version": TURN_METRICS_SCHEMA_VERSION,
        "category": str(category.get("value") or ""),
        "route_source": str(category.get("source") or ""),
        "roles": {str(k): str(v) for k, v in roles.items()},
        "agents": list(turn.get("agents") or []),
        "rounds_used": int(turn.get("agent_parallel_rounds") or 0),
        "escalated": bool(category.get("escalated_from")),
        "objection_summary": objection_summary,
        "objection_resolution": objection_resolution,
        "consensus_reached": str(consensus.get("status") or "") == "reached",
        "synthesized": bool(turn.get("synthesize")),
        "latency_ms": int(turn.get("latency_ms") or 0),
        "oracle_rollup": _oracle_rollup(executions),
        "advisor_rationale": category.get("advisor_rationale"),  # set by feedback_advisor (Phase B)
        "advisor_source": category.get("advisor_source"),  # "history"|"explore" (S1.5)
        "advisor_combo_id": category.get("advisor_combo_id"),  # role-combo key (S1.5)
        "tool_card_suggestions": category.get("tool_card_suggestions") or [],  # S3a-0
        "failure_tags": failure_tags,  # HS1-1
        "primary_tag": primary_tag,  # HS1-1
    }
    return metrics
