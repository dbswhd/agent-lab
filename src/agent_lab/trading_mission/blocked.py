"""Write stub artifacts when preflight blocks trading."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_lab.plan.paths import write_trading_plan_md
from agent_lab.trading_mission.export_batch import write_proposal_batch
from agent_lab.trading_mission.topic import mission_id_from_date

_KST = timezone(timedelta(hours=9))


def write_blocked_artifacts(
    session_folder: Path,
    snapshot: dict[str, Any],
    *,
    reason: str | None = None,
) -> None:
    freshness = snapshot.get("freshness") or {}
    blocking_reason = reason or str(freshness.get("message") or "trade not allowed")
    if snapshot.get("kill_switch"):
        blocking_reason = "kill_switch active"

    artifacts = session_folder / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    plan_md = f"""# Trading Mission plan (blocked)

## 합의
- ingest_ready: false
- blocking_reason: {blocking_reason}
- active_strategies: []
- discuss_rounds_used: 0

## 지금 논의 중인 것
장전 preflight가 trade를 차단해 Room discuss를 생략했다.

## 합의된 점
- proposal 0건
- Human은 데이터 refresh 또는 kill switch 해제 후 재실행

## 에이전트별 핵심
- **PREFLIGHT:** snapshot only
"""
    write_trading_plan_md(session_folder, plan_md)

    playbook = f"""# 오늘 장중 행동 — {datetime.now(_KST).strftime("%Y-%m-%d")}

## 상태
- ingest_ready: false
- blocking: {blocking_reason}

## 오늘 장중 행동
- **거래 보류** — thin agent는 신규 proposal 제출 금지
- 데이터 정상화 후 Trading Mission 재실행

## 금지
- FAIL ref proposal
- LIVE execute
"""
    (artifacts / "playbook.md").write_text(playbook, encoding="utf-8")

    summary = f"""# Mission summary (blocked)

- as_of: {snapshot.get("as_of")}
- reason: {blocking_reason}
- trade_allowed: false
"""
    (artifacts / "mission_summary.md").write_text(summary, encoding="utf-8")

    batch = {
        "mission_id": mission_id_from_date(),
        "session_id": session_folder.name,
        "ingest_ready": False,
        "consensus": {
            "ingest_ready": False,
            "blocking_reason": blocking_reason,
            "active_strategies": [],
        },
        "proposals": [],
        "generated_at": datetime.now(_KST).isoformat(),
    }
    write_proposal_batch(session_folder, batch)
