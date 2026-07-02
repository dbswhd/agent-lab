"""Session template routing hints."""

from __future__ import annotations

from agent_lab.session.routing_hints import template_routing_hints
from agent_lab.topic_router import resolve_topic_route


def test_template_routing_hints_trading_mission() -> None:
    hints = template_routing_hints("trading-mission")
    assert hints.get("response_contract_bias") == "evidence_first"


def test_topic_router_imports_routing_hints(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TOPIC_ROUTER", "1")
    route = resolve_topic_route(
        "premarket snapshot review",
        session_template="trading-mission",
    )
    assert route.category in {"trading", "standard", "deep", "quick", "critical"}
