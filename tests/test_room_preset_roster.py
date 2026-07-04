"""§3.2.1 Room preset roster promotion (fast → supervisor)."""

from __future__ import annotations

from agent_lab.room.preset import resolve_preset_for_roster


def test_fast_roster_one_stays_fast() -> None:
    preset, promoted = resolve_preset_for_roster("fast", 1)
    assert preset == "fast"
    assert promoted is None


def test_fast_roster_two_promotes_supervisor() -> None:
    preset, promoted = resolve_preset_for_roster("fast", 2)
    assert preset == "supervisor"
    assert promoted == "fast"


def test_supervisor_roster_uncapped() -> None:
    preset, promoted = resolve_preset_for_roster("supervisor", 5)
    assert preset == "supervisor"
    assert promoted is None


def test_unknown_preset_passthrough() -> None:
    preset, promoted = resolve_preset_for_roster("custom", 3)
    assert preset == "custom"
    assert promoted is None
