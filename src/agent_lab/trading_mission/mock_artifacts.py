"""Seed Trading Mission artifacts after mock Room discuss (dev/pilot)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_CONSENSUS_SECTION = re.compile(r"##\s*합의", re.IGNORECASE)
_PLAYBOOK_HEADER = re.compile(r"오늘\s*장중\s*행동", re.IGNORECASE)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _default_proposal_from_card(card: dict[str, Any]) -> dict[str, Any]:
    ref = str(card.get("source_file") or card.get("ref") or "unknown")
    slug = str(card.get("ref") or ref.split("/")[-1].replace("_full.json", ""))
    return {
        "symbol": "069500",
        "market": "kr",
        "side": "buy",
        "quantity": 1,
        "notional": 100_000,
        "order_type": "market",
        "thesis": f"mock-room premarket rebalance via {slug}",
        "data_sources": ["overlay:kr_kospi_v1", f"card:{slug}"],
        "backtest_ref": ref,
        "confidence": 0.65,
    }


def _ensure_plan_consensus(plan_path: Path, *, ingest_ready: bool, strategies: list[str]) -> bool:
    text = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    if _CONSENSUS_SECTION.search(text) and "ingest_ready" in text.lower():
        return False

    block = "\n".join(
        [
            "## 합의",
            f"- ingest_ready: {'true' if ingest_ready else 'false'}",
            "- blocking_reason:",
            f"- active_strategies: {json.dumps(strategies, ensure_ascii=False)}",
            "- discuss_rounds_used: 1",
            "",
        ]
    )
    if text.strip():
        plan_path.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
    else:
        plan_path.write_text("# plan — Trading Mission (mock-room)\n\n" + block, encoding="utf-8")
    return True


def _ensure_playbook(playbook_path: Path, strategies: list[str]) -> bool:
    if playbook_path.is_file():
        text = playbook_path.read_text(encoding="utf-8", errors="replace")
        if _PLAYBOOK_HEADER.search(text):
            return False
    else:
        text = ""
    active = ", ".join(strategies) if strategies else "(none)"
    body = (
        "# 오늘 장중 행동\n\n"
        "## 상태\n"
        "- mode: mock-room dev\n"
        f"- active_strategies: {active}\n"
        "- approve proposals in control plane console only\n"
    )
    if text.strip():
        playbook_path.write_text(text.rstrip() + "\n\n" + body, encoding="utf-8")
    else:
        playbook_path.write_text(body, encoding="utf-8")
    return True


def ensure_mock_trading_artifacts(
    session_folder: Path,
    snapshot: dict[str, Any] | None = None,
    *,
    force_trade_allowed: bool = False,
    max_proposals: int = 1,
) -> dict[str, Any]:
    """Fill plan/playbook/draft gaps so mock Room sessions can export + ingest."""
    artifacts = session_folder / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    snap_path = artifacts / "market_snapshot.json"
    snap = snapshot if snapshot is not None else (_load_json(snap_path) or {})
    if force_trade_allowed and not snap.get("trade_allowed"):
        snap = dict(snap)
        snap["trade_allowed"] = True
        snap_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    eligible = [c for c in (snap.get("eligible_cards") or []) if isinstance(c, dict)]
    strategies = [str(c.get("ref")) for c in eligible[:3] if c.get("ref")]

    plan_changed = _ensure_plan_consensus(
        session_folder / "plan.md",
        ingest_ready=bool(snap.get("trade_allowed", True)),
        strategies=strategies,
    )
    playbook_changed = _ensure_playbook(artifacts / "playbook.md", strategies)

    draft_path = artifacts / "proposals_draft.json"
    drafts: list[dict[str, Any]] = []
    if draft_path.is_file():
        try:
            raw = json.loads(draft_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                drafts = [row for row in raw if isinstance(row, dict)]
        except (OSError, json.JSONDecodeError):
            drafts = []

    draft_changed = False
    if not drafts and eligible:
        cap = max(1, min(max_proposals, 5))
        drafts = [_default_proposal_from_card(c) for c in eligible[:cap]]
        draft_path.write_text(json.dumps(drafts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        draft_changed = True

    return {
        "ok": True,
        "plan_patched": plan_changed,
        "playbook_patched": playbook_changed,
        "draft_seeded": draft_changed,
        "proposal_count": len(drafts),
        "trade_allowed": bool(snap.get("trade_allowed")),
    }
