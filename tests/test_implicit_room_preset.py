"""P2 implicit room_preset — TurnContract topic+roster resolution."""

from __future__ import annotations

from agent_lab.room.preset import resolve_implicit_room_preset

S1_TOPIC = "room.py에서 consensus 라운드 cap 기본값이 뭐야?"


def test_implicit_multi_agent_is_supervisor() -> None:
    assert resolve_implicit_room_preset(S1_TOPIC, 3) == "supervisor"


def test_implicit_s1_anchor_stays_supervisor_with_trio() -> None:
    """Anchored quick factual lookup with 3 agents — not fast preset."""
    assert resolve_implicit_room_preset(S1_TOPIC, 3) == "supervisor"


def test_implicit_single_agent_quick_topic_is_fast() -> None:
    topic = "pytest -q 는 뭐야?"
    assert resolve_implicit_room_preset(topic, 1) == "fast"


def test_implicit_empty_roster_defaults_supervisor() -> None:
    assert resolve_implicit_room_preset("hello", 0) == "supervisor"
