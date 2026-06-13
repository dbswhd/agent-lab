"""ResearchArtifactCard — compact (~1KB) backtest summary from *_full.json."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CARD_MAX_BYTES = 2048
_PARAM_KEYS = (
    "score_mode",
    "top_n",
    "overlay_thresh",
    "overlay_hyst",
    "VIX_THR",
    "SIZE_5OF5",
    "SIZE_4OF5",
    "BEAR_TICKER",
    "COST_ONE_WAY",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def slug_from_full_path(path: Path) -> str:
    stem = path.stem
    if stem.endswith("_full"):
        stem = stem[: -len("_full")]
    # drop trailing runtag suffix like _20260601_234048
    parts = stem.rsplit("_", 2)
    if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
        return "_".join(parts[:-2])
    return stem


def _trim_params(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key in _PARAM_KEYS:
        if key in raw:
            out[key] = raw[key]
    if not out and raw:
        for key, value in list(raw.items())[:6]:
            if isinstance(value, (str, int, float, bool)) or value is None:
                out[key] = value
    return out


def _extract_verdict_block(data: dict[str, Any]) -> tuple[str, list[str], dict[str, Any], dict[str, Any]]:
    verdict = str(data.get("verdict") or data.get("meta_verdict") or "").upper()
    fails = list(data.get("fails") or [])
    params = _trim_params(data.get("params"))
    oos = data.get("OOS") if isinstance(data.get("OOS"), dict) else {}

    winner = data.get("is_winner")
    if isinstance(winner, dict):
        wv = str(winner.get("verdict") or "").upper()
        if wv:
            verdict = wv
        wf = winner.get("fails")
        if isinstance(wf, list) and wf:
            fails = [str(x) for x in wf]
        params = _trim_params(winner.get("params")) or params
        woos = winner.get("OOS")
        if isinstance(woos, dict) and woos:
            oos = woos

    if not verdict:
        verdict = "UNKNOWN"
    return verdict, fails, params, oos


def build_card_from_full_json(
    path: Path,
    pipeline_root: Path | None = None,
    *,
    built_at: str | None = None,
) -> dict[str, Any]:
    """Build a compact ResearchArtifactCard from one *_full.json file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected object json: {path}")

    verdict, fails, params, oos = _extract_verdict_block(data)
    root = pipeline_root.resolve() if pipeline_root else None
    try:
        source_file = str(path.relative_to(root)) if root else path.name
    except ValueError:
        source_file = str(path)

    card: dict[str, Any] = {
        "ref": slug_from_full_path(path),
        "strategy": str(data.get("strategy") or slug_from_full_path(path)),
        "name": str(data.get("name") or ""),
        "verdict": verdict,
        "eligible_for_proposal": verdict == "PASS",
        "oos_sharpe": oos.get("sharpe"),
        "oos_mdd": oos.get("mdd"),
        "oos_cagr": oos.get("cagr"),
        "fails": fails[:8],
        "params": params,
        "runtag": str(data.get("runtag") or ""),
        "source_file": source_file.replace("\\", "/"),
        "built_at": built_at or _utc_now_iso(),
    }
    if data.get("meta_verdict"):
        card["meta_verdict"] = str(data["meta_verdict"]).upper()

    encoded = json.dumps(card, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > CARD_MAX_BYTES:
        card["params"] = {k: card["params"][k] for k in list(card["params"])[:3]}
        card["fails"] = card["fails"][:4]
        encoded = json.dumps(card, ensure_ascii=False, separators=(",", ":"))
    card["size_bytes"] = len(encoded.encode("utf-8"))
    return card


def write_card_cache(cards_dir: Path, card: dict[str, Any]) -> Path:
    cards_dir.mkdir(parents=True, exist_ok=True)
    ref = str(card.get("ref") or "unknown")
    out = cards_dir / f"{ref}.json"
    out.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
