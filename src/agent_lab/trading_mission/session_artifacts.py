"""Post-Room artifact helpers — playbook seal, preflight context for agents."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_PLAYBOOK_HEADER = re.compile(r"오늘\s*장중\s*행동", re.IGNORECASE)
_CONSENSUS_INGEST = re.compile(r"ingest_ready\s*:\s*(true|false)", re.IGNORECASE)
_CONSENSUS_BLOCKING = re.compile(r"blocking_reason\s*:\s*(.+)", re.IGNORECASE)
_CONSENSUS_STRATEGIES = re.compile(r"active_strategies\s*:\s*\[([^\]]*)\]", re.IGNORECASE)

_KST = timezone(timedelta(hours=9))


def _parse_plan_consensus(plan_md: str) -> dict[str, Any]:
    text = plan_md or ""
    ingest = False
    m = _CONSENSUS_INGEST.search(text)
    if m:
        ingest = m.group(1).lower() == "true"
    blocking_reason = ""
    m = _CONSENSUS_BLOCKING.search(text)
    if m:
        blocking_reason = m.group(1).strip()
    strategies: list[str] = []
    m = _CONSENSUS_STRATEGIES.search(text)
    if m:
        inner = m.group(1)
        strategies = [
            s.strip().strip('"').strip("'")
            for s in inner.split(",")
            if s.strip()
        ]
    return {
        "ingest_ready": ingest,
        "blocking_reason": blocking_reason,
        "active_strategies": strategies,
    }


def build_preflight_seal(session_folder: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compact deterministic facts for Room agents (session-local paths)."""
    freshness = snapshot.get("freshness") if isinstance(snapshot.get("freshness"), dict) else {}
    overlay = snapshot.get("overlay_signals") if isinstance(snapshot.get("overlay_signals"), dict) else {}
    kospi = overlay.get("kr_kospi_v1") if isinstance(overlay.get("kr_kospi_v1"), dict) else {}
    recent = kospi.get("recent_actions")
    last_action = recent[0] if isinstance(recent, list) and recent else {}
    signal = last_action.get("signal") if isinstance(last_action.get("signal"), dict) else {}
    return {
        "session_folder": str(session_folder.resolve()),
        "market_snapshot_path": str((session_folder / "artifacts" / "market_snapshot.json").resolve()),
        "trade_allowed": bool(snapshot.get("trade_allowed")),
        "freshness_ok": bool(freshness.get("ok")),
        "freshness_blocking": bool(freshness.get("blocking")),
        "freshness_message": str(freshness.get("message") or ""),
        "kill_switch": bool(snapshot.get("kill_switch")),
        "eligible_card_count": len(snapshot.get("eligible_cards") or []),
        "overlay_kr_kospi_v1": {
            "position": kospi.get("position"),
            "flag": kospi.get("flag"),
            "action": kospi.get("action"),
            "signal_date": signal.get("signal_date"),
            "kr_data_last": signal.get("kr_data_last"),
            "us_data_last": signal.get("us_data_last"),
        },
    }


def append_preflight_seal_to_topic(
    session_folder: Path,
    topic: str,
    snapshot: dict[str, Any],
) -> str:
    """Append sealed preflight JSON so agents read session snapshot, not pipeline root."""
    seal = build_preflight_seal(session_folder, snapshot)
    block = (
        "\n\n## PREFLIGHT SEAL (deterministic — session `artifacts/market_snapshot.json`)\n"
        "Room은 **이 세션 폴더**의 `artifacts/market_snapshot.json`만 근거로 사용한다. "
        "`pipeline/artifacts/` 경로는 존재하지 않는다.\n\n"
        f"```json\n{json.dumps(seal, ensure_ascii=False, indent=2)}\n```\n"
    )
    merged = topic.rstrip() + block
    (session_folder / "topic.txt").write_text(merged, encoding="utf-8")
    return merged


def ensure_playbook_after_room(session_folder: Path) -> bool:
    """Write playbook.md from plan consensus when Scribe omitted it."""
    artifacts = session_folder / "artifacts"
    playbook_path = artifacts / "playbook.md"
    if playbook_path.is_file():
        text = playbook_path.read_text(encoding="utf-8", errors="replace")
        if _PLAYBOOK_HEADER.search(text):
            return False

    plan_path = session_folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8", errors="replace") if plan_path.is_file() else ""
    consensus = _parse_plan_consensus(plan_md)
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    active = ", ".join(consensus["active_strategies"]) if consensus["active_strategies"] else "(none)"
    blocking = consensus["blocking_reason"] or "(none)"
    mode = "ingest_ready" if consensus["ingest_ready"] else "hold"

    body = f"""# 오늘 장중 행동 — {today}

## 상태
- ingest_ready: {str(consensus['ingest_ready']).lower()}
- mode: {mode}
- blocking_reason: {blocking}
- active_strategies: {active}

## 오늘 장중 행동
- pending proposal 만료 전 Human approve 요청만 — thesis 재작성 금지
- overlay `ACTION_REQUIRED.flag` 발생 시 delta mission 트리거 (Human)
- freshness 재확인: `get_data_freshness()` 또는 preflight snapshot

## 금지
- FAIL ref proposal
- LIVE execute
- 신규 full Room / backtest refresh (dry_run=False)
"""
    playbook_path.write_text(body, encoding="utf-8")
    return True
