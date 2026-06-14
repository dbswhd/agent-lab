"""Read-only pipeline research/kr/results → ResearchArtifactCard build + cache."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_lab.extensions.quant_trading import require_pipeline_root
from agent_lab.research_artifact_card import (
    build_card_from_full_json,
    slug_from_full_path,
    write_card_cache,
)

_RESULTS_GLOB = "**/*_full.json"


def resolve_pipeline_root(explicit: Path | str | None = None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"pipeline root not found: {root}")
        return root
    try:
        return require_pipeline_root()
    except FileNotFoundError as exc:
        raise FileNotFoundError(str(exc)) from exc


def default_cards_dir(pipeline: Path | None = None) -> Path:
    root = pipeline or resolve_pipeline_root()
    override = (os.getenv("AGENTIC_TRADING_CARDS_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return root / "data" / "agentic_trading" / "cards"


def discover_full_json_files(pipeline: Path) -> list[Path]:
    results = pipeline / "research" / "kr" / "results"
    if not results.is_dir():
        return []
    return sorted(results.rglob("*_full.json"))


def _pick_latest_for_ref(paths: list[Path]) -> Path:
    return max(paths, key=lambda p: (p.stat().st_mtime, p.name))


def index_latest_full_json(pipeline: Path) -> dict[str, Path]:
    """Map card ref → newest *_full.json path."""
    by_ref: dict[str, list[Path]] = {}
    for path in discover_full_json_files(pipeline):
        ref = slug_from_full_path(path)
        by_ref.setdefault(ref, []).append(path)
    return {ref: _pick_latest_for_ref(items) for ref, items in by_ref.items()}


def _resolve_source_path(pipeline: Path, ref: str) -> Path | None:
    text = (ref or "").strip().replace("\\", "/")
    if not text:
        return None

    if text.endswith("_full.json"):
        candidate = pipeline / text
        if candidate.is_file():
            return candidate.resolve()
        # allow path relative to results root
        alt = pipeline / "research" / "kr" / "results" / Path(text).name
        if alt.is_file():
            return alt.resolve()

    index = index_latest_full_json(pipeline)
    if text in index:
        return index[text]

    lowered = text.lower()
    for key, path in index.items():
        if key.lower() == lowered:
            return path
        if lowered in path.name.lower():
            return path
    return None


def load_cached_card(ref: str, *, pipeline: Path | None = None, cards_dir: Path | None = None) -> dict[str, Any] | None:
    root = pipeline or resolve_pipeline_root()
    cache_dir = cards_dir or default_cards_dir(root)
    slug = slug_from_full_path(Path(ref)) if ref.endswith(".json") else ref.strip()
    path = cache_dir / f"{slug}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def get_backtest_card(
    ref: str,
    *,
    pipeline: Path | None = None,
    prefer_cache: bool = True,
) -> dict[str, Any]:
    """Return ResearchArtifactCard for ref (slug, path fragment, or source_file)."""
    root = pipeline or resolve_pipeline_root()
    if prefer_cache:
        cached = load_cached_card(ref, pipeline=root)
        if cached is not None:
            return {"ok": True, "card": cached, "source": "cache"}

    source = _resolve_source_path(root, ref)
    if source is None:
        return {"ok": False, "reason": "ref not found", "ref": ref}

    try:
        card = build_card_from_full_json(source, root)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "reason": str(exc), "ref": ref, "source_file": str(source)}

    return {"ok": True, "card": card, "source": "full_json", "source_file": card.get("source_file")}


def get_strategy_verdict(ref: str, *, pipeline: Path | None = None) -> dict[str, Any]:
    """Compact verdict read for MCP (no full JSON)."""
    payload = get_backtest_card(ref, pipeline=pipeline)
    if not payload.get("ok"):
        return payload
    card = payload["card"]
    return {
        "ok": True,
        "ref": card.get("ref"),
        "verdict": card.get("verdict"),
        "eligible_for_proposal": bool(card.get("eligible_for_proposal")),
        "oos_sharpe": card.get("oos_sharpe"),
        "oos_mdd": card.get("oos_mdd"),
        "fails": card.get("fails") or [],
        "source_file": card.get("source_file"),
        "built_at": card.get("built_at"),
    }


def list_wireup_candidates(
    *,
    pipeline: Path | None = None,
    prefer_cache: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    """PASS cards with eligible_for_proposal=true."""
    root = pipeline or resolve_pipeline_root()
    cap = max(1, min(int(limit or 50), 200))
    cards: list[dict[str, Any]] = []

    if prefer_cache and default_cards_dir(root).is_dir():
        for path in sorted(default_cards_dir(root).glob("*.json")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(row, dict) and row.get("eligible_for_proposal"):
                cards.append(row)
    else:
        for ref, source in index_latest_full_json(root).items():
            try:
                row = build_card_from_full_json(source, root)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if row.get("eligible_for_proposal"):
                cards.append(row)

    cards.sort(key=lambda c: (c.get("oos_sharpe") or 0), reverse=True)
    cards = cards[:cap]
    return {
        "ok": True,
        "count": len(cards),
        "refs": [c.get("ref") for c in cards if c.get("ref")],
        "cards": cards,
    }


def sync_research_cards(
    pipeline: Path | None = None,
    *,
    cards_dir: Path | None = None,
    include_ineligible: bool = True,
) -> dict[str, Any]:
    """Build/update data/agentic_trading/cards/*.json from research/kr/results."""
    root = pipeline or resolve_pipeline_root()
    out_dir = cards_dir or default_cards_dir(root)
    index = index_latest_full_json(root)

    written: list[str] = []
    skipped: list[str] = []
    errors: list[dict[str, str]] = []

    for ref, source in sorted(index.items()):
        try:
            card = build_card_from_full_json(source, root)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append({"ref": ref, "error": str(exc)})
            continue
        if not include_ineligible and not card.get("eligible_for_proposal"):
            skipped.append(ref)
            continue
        write_card_cache(out_dir, card)
        written.append(ref)

    return {
        "ok": not errors,
        "pipeline_root": str(root),
        "cards_dir": str(out_dir),
        "written": len(written),
        "skipped_ineligible": len(skipped),
        "refs": written,
        "errors": errors,
    }


def cards_cache_stale(
    pipeline: Path | None = None,
    *,
    cards_dir: Path | None = None,
) -> bool:
    """True when any source *_full.json is newer than the card cache."""
    root = pipeline or resolve_pipeline_root()
    out_dir = cards_dir or default_cards_dir(root)
    index = index_latest_full_json(root)
    if not index:
        return False
    latest_source = max(path.stat().st_mtime for path in index.values())
    if not out_dir.is_dir():
        return True
    cache_files = list(out_dir.glob("*.json"))
    if not cache_files:
        return True
    latest_cache = max(path.stat().st_mtime for path in cache_files)
    return latest_source > latest_cache + 1.0


def sync_research_cards_if_stale(
    pipeline: Path | None = None,
    *,
    cards_dir: Path | None = None,
    include_ineligible: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Rebuild card cache only when research results changed (or force=True)."""
    root = pipeline or resolve_pipeline_root()
    out_dir = cards_dir or default_cards_dir(root)
    if not force and not cards_cache_stale(root, cards_dir=out_dir):
        return {
            "ok": True,
            "skipped": True,
            "reason": "cache fresh",
            "pipeline_root": str(root),
            "cards_dir": str(out_dir),
            "written": 0,
        }
    report = sync_research_cards(
        root,
        cards_dir=out_dir,
        include_ineligible=include_ineligible,
    )
    report["skipped"] = False
    return report


def load_all_cached_cards(
    pipeline: Path | None = None,
    *,
    cards_dir: Path | None = None,
) -> list[dict[str, Any]]:
    root = pipeline or resolve_pipeline_root()
    cache_dir = cards_dir or default_cards_dir(root)
    cards: list[dict[str, Any]] = []
    if not cache_dir.is_dir():
        return cards
    for path in sorted(cache_dir.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(row, dict):
            cards.append(row)
    return cards


def compact_card_index(cards: list[dict[str, Any]], *, limit: int = 40) -> list[dict[str, Any]]:
    """Minimal ref/verdict/eligible rows for market_snapshot (no full params)."""
    cap = max(1, min(int(limit or 40), 100))
    rows: list[dict[str, Any]] = []
    for card in cards[:cap]:
        rows.append(
            {
                "ref": card.get("ref"),
                "verdict": card.get("verdict"),
                "eligible_for_proposal": bool(card.get("eligible_for_proposal")),
                "oos_sharpe": card.get("oos_sharpe"),
                "source_file": card.get("source_file"),
            }
        )
    return rows
