"""Research artifact card helpers for Trading Mission preflight/verify."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_lab.pipeline_research_read import (
    compact_card_index,
    load_all_cached_cards,
    sync_research_cards_if_stale,
)
from agent_lab.research.artifact_card import build_card_from_full_json


def ensure_research_cards(
    pipeline: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Sync PASS+FAIL cards from research/kr/results when cache is stale."""
    return sync_research_cards_if_stale(pipeline, include_ineligible=True, force=force)


def load_strategy_cards(pipeline: Path) -> list[dict[str, Any]]:
    """All cached cards; rebuild from *_full.json if cache empty."""
    cards = load_all_cached_cards(pipeline)
    if cards:
        return cards

    results_root = pipeline / "research" / "kr" / "results"
    if not results_root.is_dir():
        return []

    index: dict[str, Path] = {}
    for path in sorted(results_root.rglob("*_full.json")):
        from agent_lab.pipeline_research_read import slug_from_full_path

        ref = slug_from_full_path(path)
        prev = index.get(ref)
        if prev is None or path.stat().st_mtime > prev.stat().st_mtime:
            index[ref] = path

    built: list[dict[str, Any]] = []
    for path in index.values():
        try:
            built.append(build_card_from_full_json(path, pipeline))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return built


def eligible_cards(cards: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    eligible = [c for c in cards if c.get("eligible_for_proposal")]
    eligible.sort(key=lambda c: c.get("oos_sharpe") or 0, reverse=True)
    return eligible[: max(1, min(limit, 50))]


def proposal_uses_fail_ref(
    proposal: dict[str, Any],
    *,
    pipeline: Path | None = None,
    snapshot: dict[str, Any] | None = None,
) -> bool:
    """True when backtest_ref resolves to FAIL / ineligible card."""
    _ = pipeline
    from agent_lab.extensions.quant_runtime import load_quant_module

    mod = load_quant_module("quant_pipeline.agentic_trading.confidence")
    if mod is not None:
        return mod.proposal_uses_fail_ref(proposal, snapshot=snapshot, pipeline=pipeline)

    ref = str(proposal.get("backtest_ref") or "").strip()
    if not ref:
        return False
    lowered = ref.lower()
    return (
        lowered.endswith("_fail.json")
        or "/fail/" in lowered
        or "verdict_fail" in lowered
        or "_fail_full.json" in lowered
        or "_fail_" in lowered
    )


def cards_snapshot_fields(
    pipeline: Path,
    *,
    sync_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cards = load_strategy_cards(pipeline)
    eligible = eligible_cards(cards)
    return {
        "cards_sync": sync_report or {},
        "strategy_cards_count": len(cards),
        "eligible_cards_count": len(eligible),
        "eligible_cards": eligible,
        "eligible_refs": [c.get("ref") for c in eligible if c.get("ref")],
        "strategy_card_index": compact_card_index(cards),
        "ineligible_refs": [c.get("ref") for c in cards if c.get("ref") and not c.get("eligible_for_proposal")],
    }
