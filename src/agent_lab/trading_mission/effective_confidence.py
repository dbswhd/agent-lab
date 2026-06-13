"""effective_confidence for Trading Mission export/ingest (agent-lab side)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_lab.pipeline_research_read import get_strategy_verdict
from agent_lab.trading_mission.artifact_cards import proposal_uses_fail_ref


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def human_confidence_threshold() -> float:
    raw = (os.getenv("AGENTIC_CONFIDENCE_HUMAN_THRESHOLD") or "0.6").strip()
    try:
        return _clamp(float(raw))
    except (TypeError, ValueError):
        return 0.6


def critic_review_from_draft(draft: dict[str, Any]) -> dict[str, Any] | None:
    raw = draft.get("critic_review")
    if isinstance(raw, dict):
        return raw
    return None


def critic_needs_human(draft: dict[str, Any]) -> bool:
    review = critic_review_from_draft(draft)
    if review is None:
        return False
    if review.get("needs_human") is True:
        return True
    objections = review.get("objections")
    if isinstance(objections, list) and any(str(x).strip() for x in objections):
        return True
    missing = review.get("missing_evidence")
    return isinstance(missing, list) and any(str(x).strip() for x in missing)


def verdict_score_from_payload(payload: dict[str, Any]) -> float:
    if not payload.get("ok"):
        return 0.35
    verdict = str(payload.get("verdict") or "").upper()
    if verdict == "FAIL" or payload.get("eligible_for_proposal") is False:
        return 0.0
    if verdict in {"INFO", "UNKNOWN", ""}:
        return 0.4
    try:
        sharpe = float(payload.get("oos_sharpe") if payload.get("oos_sharpe") is not None else 1.0)
    except (TypeError, ValueError):
        sharpe = 1.0
    cap = _clamp(0.55 + sharpe * 0.08)
    fails = payload.get("fails") or []
    if fails:
        cap = min(cap, 0.45)
    return _clamp(cap)


def resolve_verdict_score(
    draft: dict[str, Any],
    *,
    pipeline: Path | None = None,
    snapshot: dict[str, Any] | None = None,
) -> float:
    ref = str(draft.get("backtest_ref") or "").strip()
    if not ref:
        return 0.35
    if proposal_uses_fail_ref(draft, pipeline=pipeline, snapshot=snapshot):
        return 0.0
    root = pipeline
    if root is None and snapshot and snapshot.get("pipeline_root"):
        root = Path(str(snapshot["pipeline_root"])).expanduser()
    payload = get_strategy_verdict(ref, pipeline=root) if root else get_strategy_verdict(ref)
    return verdict_score_from_payload(payload)


def freshness_score_from_snapshot(snapshot: dict[str, Any] | None) -> float | None:
    if not snapshot:
        return None
    if snapshot.get("trade_allowed") is False:
        return 0.0
    freshness = snapshot.get("freshness")
    if isinstance(freshness, dict):
        if freshness.get("blocking"):
            return 0.0
        if freshness.get("ok") is False:
            return 0.25
        return 1.0
    return None


def portfolio_fit_score(draft: dict[str, Any], snapshot: dict[str, Any] | None) -> float:
    portfolio = snapshot.get("portfolio") if isinstance(snapshot, dict) else None
    if not isinstance(portfolio, dict):
        return 1.0
    try:
        cash = float(portfolio.get("cash") or 0)
        equity = float(portfolio.get("equity") or 0)
        notional = float(draft.get("notional") or 0)
    except (TypeError, ValueError):
        return 0.5
    if notional <= 0:
        return 0.0
    if notional > cash:
        return 0.35
    if equity <= 0:
        return 0.5
    positions = portfolio.get("positions") if isinstance(portfolio.get("positions"), dict) else {}
    symbol = str(draft.get("symbol") or "").strip().upper()
    try:
        current = float(positions.get(symbol, 0))
    except (TypeError, ValueError):
        current = 0.0
    weight = (current + notional) / equity
    if weight > 0.35:
        return 0.45
    if weight > 0.25:
        return 0.6
    return 1.0


def effective_confidence(
    draft: dict[str, Any],
    *,
    ingest_ready: bool = True,
    trade_allowed: bool | None = None,
    snapshot: dict[str, Any] | None = None,
    pipeline: Path | None = None,
) -> float:
    try:
        base = float(draft.get("confidence", 0))
    except (TypeError, ValueError):
        base = 0.0
    base = _clamp(base)

    if proposal_uses_fail_ref(draft, pipeline=pipeline, snapshot=snapshot):
        return 0.0

    components = [
        base,
        resolve_verdict_score(draft, pipeline=pipeline, snapshot=snapshot),
        portfolio_fit_score(draft, snapshot),
    ]
    fresh = freshness_score_from_snapshot(snapshot)
    if fresh is not None:
        components.append(_clamp(fresh))

    review = critic_review_from_draft(draft)
    if review is not None:
        try:
            components.append(_clamp(float(review.get("confidence_cap", base))))
        except (TypeError, ValueError):
            pass

    score = _clamp(min(components))
    if not ingest_ready:
        score = _clamp(score * 0.25)
    elif trade_allowed is False:
        score = _clamp(score * 0.5)
    return score


def proposal_needs_human(
    draft: dict[str, Any],
    *,
    effective: float | None = None,
    snapshot: dict[str, Any] | None = None,
    pipeline: Path | None = None,
    ingest_ready: bool = True,
    trade_allowed: bool | None = None,
) -> bool:
    if critic_needs_human(draft):
        return True
    score = (
        effective
        if effective is not None
        else effective_confidence(
            draft,
            ingest_ready=ingest_ready,
            trade_allowed=trade_allowed,
            snapshot=snapshot,
            pipeline=pipeline,
        )
    )
    return score < human_confidence_threshold()


def batch_context_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Fields to embed in proposal_batch for native ingest."""
    fresh = snapshot.get("freshness") if isinstance(snapshot.get("freshness"), dict) else {}
    fresh_score = freshness_score_from_snapshot(snapshot)
    return {
        "trade_allowed": bool(snapshot.get("trade_allowed", True)),
        "freshness": fresh,
        "freshness_score": fresh_score,
        "kill_switch": snapshot.get("kill_switch"),
    }
