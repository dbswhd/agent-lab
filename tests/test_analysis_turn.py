"""Analysis turn guidance in context bundle."""

from __future__ import annotations

from agent_lab.context_bundle import build_context_bundle
from agent_lab.room_context import ANALYSIS_TURN_GUIDANCE


class _Msg:
    role: str = "user"
    content: str = "topic"
    agent: str | None = None


def test_analysis_turn_injects_guidance():
    run_meta = {"turn_profile": "analyze"}
    bundle = build_context_bundle(
        "topic",
        [_Msg()],
        "claude",
        run_meta=run_meta,
    )
    text = bundle.render()
    assert ANALYSIS_TURN_GUIDANCE.splitlines()[0] in text
    assert "현황 파악" in text
