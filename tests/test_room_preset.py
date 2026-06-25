"""Tests for Room Preset System (P1-5)."""

from __future__ import annotations

import pytest

from agent_lab.room_preset import (
    RoomPresetConfig,
    default_room_preset,
    list_presets,
    preset_catalog,
    preset_turn_profile,
    resolve_preset,
)

_VALID_TURN_PROFILES = frozenset(
    {"quick", "team", "analyze", "discuss", "free", "verified", "specialist", "loop"}
)


def test_resolve_preset_fast() -> None:
    cfg = resolve_preset("fast")
    assert cfg is not None
    assert cfg.preset == "fast"
    assert cfg.turn_profile == "quick"


def test_resolve_preset_consensus() -> None:
    cfg = resolve_preset("consensus")
    assert cfg is not None
    assert cfg.turn_profile == "team"


def test_resolve_preset_pipeline_maps_to_specialist() -> None:
    cfg = resolve_preset("pipeline")
    assert cfg is not None
    assert cfg.turn_profile == "specialist"


def test_resolve_preset_producer_reviewer_maps_to_verified() -> None:
    cfg = resolve_preset("producer_reviewer")
    assert cfg is not None
    assert cfg.turn_profile == "verified"


def test_resolve_preset_supervisor_maps_to_loop() -> None:
    cfg = resolve_preset("supervisor")
    assert cfg is not None
    assert cfg.turn_profile == "loop"


def test_resolve_preset_expert_pool_maps_to_team() -> None:
    cfg = resolve_preset("expert_pool")
    assert cfg is not None
    assert cfg.turn_profile == "team"


def test_resolve_preset_unknown_returns_none() -> None:
    assert resolve_preset("ultra") is None
    assert resolve_preset("") is None


def test_resolve_preset_none_returns_none() -> None:
    assert resolve_preset(None) is None


def test_resolve_preset_case_insensitive() -> None:
    assert resolve_preset("FAST") is not None
    assert resolve_preset("Supervisor") is not None
    assert resolve_preset("PIPELINE") is not None


def test_default_room_preset_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ROOM_PRESET", raising=False)
    assert default_room_preset() is None


def test_default_room_preset_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ROOM_PRESET", "fast")
    assert default_room_preset() == "fast"


def test_default_room_preset_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ROOM_PRESET", "ultra")
    assert default_room_preset() is None


def test_default_room_preset_case_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ROOM_PRESET", "CONSENSUS")
    assert default_room_preset() == "consensus"


def test_list_presets_count() -> None:
    presets = list_presets()
    assert len(presets) == 6


def test_list_presets_stable_order() -> None:
    ids = [cfg.preset for cfg in list_presets()]
    assert ids == ["fast", "consensus", "expert_pool", "producer_reviewer", "pipeline", "supervisor"]


def test_list_presets_all_configs() -> None:
    for cfg in list_presets():
        assert isinstance(cfg, RoomPresetConfig)
        assert cfg.turn_profile in _VALID_TURN_PROFILES
        assert cfg.description


def test_preset_turn_profile_resolves_known() -> None:
    assert preset_turn_profile("fast") == "quick"
    assert preset_turn_profile("pipeline") == "specialist"


def test_preset_turn_profile_fallback_on_unknown() -> None:
    assert preset_turn_profile("unknown", fallback="discuss") == "discuss"


def test_preset_turn_profile_fallback_on_none() -> None:
    assert preset_turn_profile(None, fallback="team") == "team"


def test_preset_catalog_shape() -> None:
    cat = preset_catalog()
    assert "presets" in cat
    assert "default" in cat
    assert len(cat["presets"]) == 6


def test_preset_catalog_preset_fields() -> None:
    cat = preset_catalog()
    for row in cat["presets"]:
        assert "id" in row
        assert "turn_profile" in row
        assert "description" in row
        assert row["turn_profile"] in _VALID_TURN_PROFILES


def test_preset_catalog_default_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ROOM_PRESET", raising=False)
    assert preset_catalog()["default"] is None


def test_preset_catalog_default_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ROOM_PRESET", "supervisor")
    assert preset_catalog()["default"] == "supervisor"
