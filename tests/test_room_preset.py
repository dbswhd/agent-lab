"""Tests for Room Preset System (P1-5)."""

from __future__ import annotations

import pytest

from agent_lab.room_preset import (
    RoomPresetConfig,
    default_room_preset,
    list_presets,
    normalize_role_policy,
    preset_catalog,
    preset_role_policy,
    preset_turn_profile,
    resolve_preset,
    resolve_role_policy,
)

_VALID_TURN_PROFILES = frozenset(
    {"quick", "team", "analyze", "discuss", "free", "verified", "specialist", "loop"}
)


def test_resolve_preset_fast() -> None:
    cfg = resolve_preset("fast")
    assert cfg is not None
    assert cfg.preset == "fast"
    assert cfg.turn_profile == "quick"
    assert cfg.role_policy == "off"


def test_resolve_preset_supervisor_maps_to_loop() -> None:
    cfg = resolve_preset("supervisor")
    assert cfg is not None
    assert cfg.turn_profile == "loop"
    assert cfg.role_policy == "auto"


def test_removed_presets_return_none() -> None:
    for legacy in ("consensus", "expert_pool", "producer_reviewer", "pipeline"):
        assert resolve_preset(legacy) is None


def test_resolve_preset_unknown_returns_none() -> None:
    assert resolve_preset("ultra") is None
    assert resolve_preset("") is None


def test_resolve_preset_none_returns_none() -> None:
    assert resolve_preset(None) is None


def test_resolve_preset_case_insensitive() -> None:
    assert resolve_preset("FAST") is not None
    assert resolve_preset("Supervisor") is not None


def test_default_room_preset_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ROOM_PRESET", raising=False)
    assert default_room_preset() is None


def test_default_room_preset_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ROOM_PRESET", "fast")
    assert default_room_preset() == "fast"


def test_default_room_preset_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ROOM_PRESET", "consensus")
    assert default_room_preset() is None


def test_default_room_preset_case_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ROOM_PRESET", "SUPERVISOR")
    assert default_room_preset() == "supervisor"


def test_list_presets_count() -> None:
    presets = list_presets()
    assert len(presets) == 2


def test_list_presets_stable_order() -> None:
    ids = [cfg.preset for cfg in list_presets()]
    assert ids == ["fast", "supervisor"]


def test_list_presets_all_configs() -> None:
    for cfg in list_presets():
        assert isinstance(cfg, RoomPresetConfig)
        assert cfg.turn_profile in _VALID_TURN_PROFILES
        assert cfg.description


def test_preset_turn_profile_resolves_known() -> None:
    assert preset_turn_profile("fast") == "quick"
    assert preset_turn_profile("supervisor") == "loop"
    assert preset_turn_profile("consensus", fallback="discuss") == "discuss"


def test_preset_turn_profile_fallback_on_unknown() -> None:
    assert preset_turn_profile("unknown", fallback="discuss") == "discuss"


def test_preset_turn_profile_fallback_on_none() -> None:
    assert preset_turn_profile(None, fallback="team") == "team"


def test_preset_role_policy() -> None:
    assert preset_role_policy("fast") == "off"
    assert preset_role_policy("supervisor") == "auto"
    assert preset_role_policy("consensus") == "auto"


def test_normalize_role_policy() -> None:
    assert normalize_role_policy("force") == "force"
    assert normalize_role_policy("OFF") == "off"
    assert normalize_role_policy("bogus") == "auto"


def test_resolve_role_policy_explicit_run_meta() -> None:
    assert resolve_role_policy({"role_policy": "force"}) == "force"


def test_resolve_role_policy_from_room_preset() -> None:
    assert resolve_role_policy({"room_preset": "supervisor"}) == "auto"
    assert resolve_role_policy({"room_preset": "fast"}) == "off"


def test_is_fast_room_session() -> None:
    from agent_lab.room_preset import is_fast_room_session

    assert is_fast_room_session({"room_preset": "fast"}) is True
    assert is_fast_room_session({"room_preset": "supervisor"}) is False
    assert is_fast_room_session({"user_mode": "quick", "plan_intent": "none"}) is True
    assert is_fast_room_session({"user_mode": "quick", "plan_intent": "loop"}) is False
    assert is_fast_room_session(None) is False


def test_preset_catalog_shape() -> None:
    cat = preset_catalog()
    assert "presets" in cat
    assert "default" in cat
    assert len(cat["presets"]) == 2


def test_preset_catalog_preset_fields() -> None:
    cat = preset_catalog()
    for row in cat["presets"]:
        assert "id" in row
        assert "label" in row
        assert "turn_profile" in row
        assert "description" in row
        assert "role_policy" in row
        assert row["turn_profile"] in _VALID_TURN_PROFILES


def test_preset_catalog_default_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ROOM_PRESET", raising=False)
    assert preset_catalog()["default"] is None


def test_preset_catalog_default_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ROOM_PRESET", "supervisor")
    assert preset_catalog()["default"] == "supervisor"
