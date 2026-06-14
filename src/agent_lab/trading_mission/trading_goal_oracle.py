"""Artifact-based goal oracle for Trading Mission sessions (P1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.trading_mission.verify import trading_mission_goal_ok

DEFAULT_TRADING_GOAL_TEXT = """오늘 장전 Trading Mission을 완료한다. 다음을 모두 만족할 때 `GOAL_OK`:
1) artifacts/market_snapshot.json 존재
2) artifacts/proposal_batch.json 존재
3) FAIL verdict ref proposal 없음
4) playbook.md 「오늘 장중 행동」섹션
5) plan.md ## 합의 에 ingest_ready 명시
"""


def is_trading_mission_run(run: dict[str, Any] | None) -> bool:
    if not run:
        return False
    if str(run.get("session_template") or "") == "trading-mission":
        return True
    return str(run.get("mission_kind") or "") == "trading_premarket"


def evaluate_trading_goal(session_folder: Path) -> dict[str, Any]:
    """Deterministic artifact oracle — same checks as verify goal mode."""
    return trading_mission_goal_ok(session_folder)


def mock_trading_goal_oracle_response(
    session_folder: Path,
    goal_text: str = "",
) -> str:
    """Mock oracle response using artifact checks instead of transcript literals."""
    result = evaluate_trading_goal(session_folder)
    detail = str(result.get("detail") or "")
    if result.get("ok"):
        return (
            "VERDICT: pass\n"
            f"REASON: trading mission artifacts satisfied ({detail})\n"
            "EVIDENCE:\n"
            "- market_snapshot.json\n"
            "- proposal_batch.json\n"
            "- playbook.md 장중 행동\n"
            "- plan.md ingest_ready"
        )
    return f"VERDICT: fail\nREASON: trading mission goal not met — {detail}\nEVIDENCE:\n- {detail}"
