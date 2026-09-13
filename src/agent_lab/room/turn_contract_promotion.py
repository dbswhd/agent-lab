from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict

PromotionStage = Literal["roles", "adaptive"]

MIN_ELIGIBLE_SESSIONS = 10
MIN_WINDOW_DAYS = 7.0
MIN_PARITY = 0.995
MAX_P95_LATENCY_REGRESSION = 0.10


class PromotionReport(TypedDict):
    stage: PromotionStage
    eligible_sessions: int
    data_window_days: float
    safety_floor_violations: int
    critical_under_routing: int
    shadow_applied_parity: float
    p95_latency_ms: int | None
    shadow_p95_latency_ms: int | None
    p95_latency_regression: float | None
    malformed_rows: int
    stale_rows: int
    metrics_green: bool
    decision: Literal["BLOCK", "HUMAN_GO_REQUIRED"]
    blocking_reasons: list[str]
    human_checkpoint: str


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return None
    return timestamp.astimezone(UTC)


def _eligible_row(row: Mapping[str, Any]) -> bool:
    return (
        row.get("phase") == "turn"
        and isinstance(row.get("session_id"), str)
        and _parse_timestamp(row.get("ts")) is not None
        and isinstance(row.get("candidate_contract_id"), str)
        and isinstance(row.get("applied_contract_id"), str)
        and isinstance(row.get("risk"), str)
        and isinstance(row.get("rollout_mode"), str)
        and isinstance(row.get("shadow_applied_parity"), bool)
        and isinstance(row.get("safety_floor_satisfied"), bool)
        and isinstance(row.get("latency_ms"), (int, float))
        and not isinstance(row.get("latency_ms"), bool)
        and math.isfinite(float(row["latency_ms"]))
    )


def _latest_by_session(
    rows: Sequence[Mapping[str, Any]],
    *,
    mode: str,
    as_of: datetime,
) -> tuple[list[Mapping[str, Any]], int, int]:
    latest: dict[str, tuple[datetime, Mapping[str, Any]]] = {}
    malformed = 0
    stale = 0
    window_start = as_of - timedelta(days=MIN_WINDOW_DAYS)
    for row in rows:
        if not _eligible_row(row):
            malformed += 1
            continue
        if row.get("rollout_mode") != mode:
            continue
        timestamp = _parse_timestamp(row.get("ts"))
        session_id = str(row["session_id"])
        if timestamp is None:
            malformed += 1
            continue
        if timestamp < window_start or timestamp > as_of:
            stale += 1
            continue
        previous = latest.get(session_id)
        if previous is None or timestamp > previous[0]:
            latest[session_id] = (timestamp, row)
    return [item[1] for item in latest.values()], malformed, stale


def _p95(rows: Sequence[Mapping[str, Any]]) -> int | None:
    latencies = sorted(max(0, int(row["latency_ms"])) for row in rows)
    if not latencies:
        return None
    return latencies[math.ceil(0.95 * len(latencies)) - 1]


def build_promotion_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    stage: PromotionStage,
    as_of: datetime | None = None,
) -> PromotionReport:
    """Evaluate evidence only; a green report still requires an explicit Human GO."""
    report_time = as_of.astimezone(UTC) if as_of is not None else datetime.now(UTC)
    stage_rows, malformed, stale = _latest_by_session(rows, mode=stage, as_of=report_time)
    shadow_rows, _, _ = _latest_by_session(rows, mode="shadow", as_of=report_time)
    timestamps = [_parse_timestamp(row.get("ts")) for row in stage_rows]
    valid_timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    window_days = (
        (max(valid_timestamps) - min(valid_timestamps)).total_seconds() / 86_400
        if len(valid_timestamps) >= 2
        else 0.0
    )
    violations = sum(row["safety_floor_satisfied"] is False for row in stage_rows)
    critical_under_routing = sum(
        row.get("risk") == "high" and row.get("applied_contract_id") != "critical_review" for row in stage_rows
    )
    parity = (
        sum(row["shadow_applied_parity"] is True for row in stage_rows) / len(stage_rows) if stage_rows else 0.0
    )
    stage_p95 = _p95(stage_rows)
    shadow_p95 = _p95(shadow_rows)
    regression = (
        (stage_p95 - shadow_p95) / shadow_p95
        if stage_p95 is not None and shadow_p95 is not None and shadow_p95 > 0
        else None
    )
    reasons: list[str] = []
    if len(stage_rows) < MIN_ELIGIBLE_SESSIONS:
        reasons.append(f"eligible_sessions<{MIN_ELIGIBLE_SESSIONS}")
    if window_days < MIN_WINDOW_DAYS:
        reasons.append(f"green_window_days<{MIN_WINDOW_DAYS:g}")
    if violations:
        reasons.append("safety_floor_violations>0")
    if critical_under_routing:
        reasons.append("critical_under_routing>0")
    if parity < MIN_PARITY:
        reasons.append(f"shadow_applied_parity<{MIN_PARITY}")
    if regression is None:
        reasons.append("p95_latency_regression_unavailable")
    elif regression > MAX_P95_LATENCY_REGRESSION:
        reasons.append(f"p95_latency_regression>{MAX_P95_LATENCY_REGRESSION}")
    metrics_green = not reasons
    checkpoint = (
        "GO roles before evaluating adaptive"
        if stage == "roles"
        else "GO adaptive before changing the default"
    )
    return {
        "stage": stage,
        "eligible_sessions": len(stage_rows),
        "data_window_days": round(window_days, 3),
        "safety_floor_violations": violations,
        "critical_under_routing": critical_under_routing,
        "shadow_applied_parity": round(parity, 6),
        "p95_latency_ms": stage_p95,
        "shadow_p95_latency_ms": shadow_p95,
        "p95_latency_regression": round(regression, 6) if regression is not None else None,
        "malformed_rows": malformed,
        "stale_rows": stale,
        "metrics_green": metrics_green,
        "decision": "HUMAN_GO_REQUIRED" if metrics_green else "BLOCK",
        "blocking_reasons": reasons,
        "human_checkpoint": checkpoint,
    }
