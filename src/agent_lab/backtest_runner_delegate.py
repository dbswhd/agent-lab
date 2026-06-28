"""Backtest runner delegate — subprocess pipeline research scripts (plan_execute / Mission)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from agent_lab.pipeline_market_read import resolve_freshness_python
from agent_lab.pipeline_research_read import (
    get_strategy_verdict,
    index_latest_full_json,
    resolve_pipeline_root,
)
from agent_lab.research.artifact_card import build_card_from_full_json, write_card_cache

# ref slug → pipeline-relative script (module main).
BACKTEST_RUNNERS: dict[str, str] = {
    "kospi_v1": "research/kr/overlay/kr_kospi_v1_backtest.py",
    "vumis": "research/kr/value_up/kr_vu_meta_selection_is.py",
    "vuo": "research/kr/value_up/kr_vu_overlay.py",
    "vum": "research/kr/value_up/kr_vu_overlay_monthly.py",
    "vu": "research/kr/value_up/kr_value_up.py",
    "theme": "research/kr/theme_rotation/kr_theme_rotation.py",
    "theme_w": "research/kr/theme_rotation/kr_theme_rotation_weekly.py",
    "sr": "research/kr/sector_rotation/kr_sector_rotation.py",
    "pairs": "research/kr/pairs/kr_pairs_trading.py",
}


def list_runnable_backtests() -> dict[str, Any]:
    """Refs with a registered backtest runner script."""
    return {
        "ok": True,
        "refs": sorted(BACKTEST_RUNNERS.keys()),
        "count": len(BACKTEST_RUNNERS),
    }


def _backtest_allowed() -> bool:
    if (os.getenv("AGENT_LAB_ALLOW_BACKTEST_RUN") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    return (os.getenv("AGENT_LAB_TRADING_MISSION") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def run_backtest_delegate(
    ref: str,
    *,
    pipeline: Path | None = None,
    dry_run: bool = True,
    timeout_sec: int | None = None,
    sync_card: bool = True,
) -> dict[str, Any]:
    """
    Run a registered pipeline backtest script for ref.

    dry_run defaults True — set AGENT_LAB_ALLOW_BACKTEST_RUN=1 and dry_run=False to execute.
    Returns compact verdict summary (never full *_full.json body).
    """
    slug = (ref or "").strip().lower()
    script_rel = BACKTEST_RUNNERS.get(slug)
    if not script_rel:
        return {
            "ok": False,
            "reason": "ref not in BACKTEST_RUNNERS",
            "ref": ref,
            "available": sorted(BACKTEST_RUNNERS.keys()),
        }

    root = pipeline or resolve_pipeline_root()
    script = root / script_rel
    if not script.is_file():
        return {"ok": False, "reason": "runner script missing", "ref": slug, "script": script_rel}

    if dry_run or not _backtest_allowed():
        return {
            "ok": True,
            "dry_run": True,
            "ref": slug,
            "script": script_rel,
            "python": resolve_freshness_python(root),
            "note": "Set dry_run=False and AGENT_LAB_ALLOW_BACKTEST_RUN=1 to execute",
        }

    timeout = timeout_sec or int(os.getenv("AGENT_LAB_BACKTEST_TIMEOUT_SEC") or "900")
    python = resolve_freshness_python(root)
    try:
        proc = subprocess.run(
            [python, str(script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=max(60, timeout),
            check=False,
            env={**os.environ, "PYTHONPATH": str(root)},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "ref": slug,
            "script": script_rel,
            "error": str(exc),
        }

    stderr_tail = (proc.stderr or "").strip()[-500:]
    stdout_tail = (proc.stdout or "").strip()[-500:]
    result: dict[str, Any] = {
        "ok": proc.returncode == 0,
        "ref": slug,
        "script": script_rel,
        "exit_code": proc.returncode,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }

    if proc.returncode != 0:
        return result

    index = index_latest_full_json(root)
    source = index.get(slug)
    card_payload: dict[str, Any] | None = None
    if source is not None and source.is_file():
        try:
            card = build_card_from_full_json(source, root)
            if sync_card:
                cards_dir = root / "data" / "agentic_trading" / "cards"
                write_card_cache(cards_dir, card)
            card_payload = {
                "ref": card.get("ref"),
                "verdict": card.get("verdict"),
                "eligible_for_proposal": card.get("eligible_for_proposal"),
                "oos_sharpe": card.get("oos_sharpe"),
                "source_file": card.get("source_file"),
            }
        except (OSError, ValueError, TypeError):
            card_payload = None

    if card_payload is None:
        verdict = get_strategy_verdict(slug, pipeline=root)
        if verdict.get("ok"):
            card_payload = {
                "ref": verdict.get("ref"),
                "verdict": verdict.get("verdict"),
                "eligible_for_proposal": verdict.get("eligible_for_proposal"),
                "oos_sharpe": verdict.get("oos_sharpe"),
                "source_file": verdict.get("source_file"),
            }

    result["card"] = card_payload
    return result
