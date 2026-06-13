"""effective_confidence — delegates to quant-agentic-trading confidence (SSoT)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.extensions.quant_runtime import require_quant_module

_CONFIDENCE = "quant_pipeline.agentic_trading.confidence"


def _confidence():
    return require_quant_module(_CONFIDENCE)


def human_confidence_threshold() -> float:
    return _confidence().human_confidence_threshold()


def critic_review_from_draft(draft: dict[str, Any]) -> dict[str, Any] | None:
    return _confidence().critic_review_from_draft(draft)


def critic_needs_human(draft: dict[str, Any]) -> bool:
    return _confidence().critic_needs_human(draft)


def freshness_score_from_snapshot(snapshot: dict[str, Any] | None) -> float | None:
    return _confidence().freshness_score_from_snapshot(snapshot)


def effective_confidence(
    draft: dict[str, Any],
    *,
    ingest_ready: bool = True,
    trade_allowed: bool | None = None,
    snapshot: dict[str, Any] | None = None,
    pipeline: Path | None = None,
) -> float:
    _ = pipeline  # cards resolved via QUANT_PIPELINE_ROOT in quant runtime
    return _confidence().effective_confidence(
        draft,
        ingest_ready=ingest_ready,
        trade_allowed=trade_allowed,
        snapshot=snapshot,
        pipeline=pipeline,
    )


def proposal_needs_human(
    draft: dict[str, Any],
    *,
    effective: float | None = None,
    snapshot: dict[str, Any] | None = None,
    pipeline: Path | None = None,
    ingest_ready: bool = True,
    trade_allowed: bool | None = None,
) -> bool:
    _ = pipeline
    if _confidence().critic_needs_human(draft):
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
    return _confidence().needs_human_for_confidence(score)


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
