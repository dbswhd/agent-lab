"""Tests for Run Profile System (P1-6)."""

from __future__ import annotations

import os

import pytest

from agent_lab.run_profile import (
    RunProfileConfig,
    apply_run_profile,
    default_run_profile,
    list_profiles,
    profile_catalog,
    resolve_profile,
)

_ALL_PROFILES = ("fast", "balanced", "thorough", "autonomous")


def test_resolve_profile_fast() -> None:
    cfg = resolve_profile("fast")
    assert cfg is not None
    assert cfg.profile == "fast"


def test_resolve_profile_balanced() -> None:
    cfg = resolve_profile("balanced")
    assert cfg is not None
    assert cfg.profile == "balanced"


def test_resolve_profile_thorough() -> None:
    cfg = resolve_profile("thorough")
    assert cfg is not None
    assert cfg.profile == "thorough"


def test_resolve_profile_autonomous() -> None:
    cfg = resolve_profile("autonomous")
    assert cfg is not None
    assert cfg.profile == "autonomous"


def test_resolve_profile_unknown_returns_none() -> None:
    assert resolve_profile("ultra") is None
    assert resolve_profile("") is None


def test_resolve_profile_none_returns_none() -> None:
    assert resolve_profile(None) is None


def test_resolve_profile_case_insensitive() -> None:
    assert resolve_profile("FAST") is not None
    assert resolve_profile("Balanced") is not None


def test_default_run_profile_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_RUN_PROFILE", raising=False)
    assert default_run_profile() is None


def test_default_run_profile_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_RUN_PROFILE", "balanced")
    assert default_run_profile() == "balanced"


def test_default_run_profile_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_RUN_PROFILE", "nuclear")
    assert default_run_profile() is None


def test_default_run_profile_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_RUN_PROFILE", "THOROUGH")
    assert default_run_profile() == "thorough"


def test_list_profiles_count() -> None:
    profiles = list_profiles()
    assert len(profiles) == 4


def test_list_profiles_stable_order() -> None:
    ids = [cfg.profile for cfg in list_profiles()]
    assert ids == ["fast", "balanced", "thorough", "autonomous"]


def test_all_profiles_have_flags() -> None:
    for cfg in list_profiles():
        assert isinstance(cfg, RunProfileConfig)
        assert isinstance(cfg.flags, dict)
        assert cfg.description


def test_fast_profile_has_auto_approve() -> None:
    cfg = resolve_profile("fast")
    assert cfg is not None
    assert cfg.flags.get("AGENT_LAB_AUTO_APPROVE_THRESHOLD") == "low"
    assert cfg.flags.get("AGENT_LAB_ROOM_PRESET") == "fast"


def test_autonomous_profile_has_mission_loop() -> None:
    cfg = resolve_profile("autonomous")
    assert cfg is not None
    assert cfg.flags.get("AGENT_LAB_MISSION_LOOP") == "1"
    assert cfg.flags.get("AGENT_LAB_AUTO_APPROVE_THRESHOLD") == "medium"


def test_thorough_profile_has_adversarial_and_judge() -> None:
    cfg = resolve_profile("thorough")
    assert cfg is not None
    assert cfg.flags.get("AGENT_LAB_ADVERSARIAL_LIVE") == "1"
    assert cfg.flags.get("AGENT_LAB_JUDGE_LIVE") == "1"


def test_apply_run_profile_sets_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in resolve_profile("fast").flags:
        monkeypatch.delenv(name, raising=False)
    applied = apply_run_profile("fast")
    assert len(applied) > 0
    for name, value in applied.items():
        if value:
            assert os.environ.get(name) == value


def test_apply_run_profile_does_not_overwrite_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "high")
    apply_run_profile("fast")
    assert os.environ.get("AGENT_LAB_AUTO_APPROVE_THRESHOLD") == "high"


def test_apply_run_profile_overwrites_when_forced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD", "high")
    apply_run_profile("fast", overwrite=True)
    assert os.environ.get("AGENT_LAB_AUTO_APPROVE_THRESHOLD") == "low"


def test_apply_run_profile_unknown_returns_empty() -> None:
    result = apply_run_profile("unknown")
    assert result == {}


def test_apply_run_profile_none_returns_empty() -> None:
    result = apply_run_profile(None)
    assert result == {}


def test_profile_catalog_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_RUN_PROFILE", raising=False)
    cat = profile_catalog()
    assert "profiles" in cat
    assert "default" in cat
    assert "active" in cat
    assert len(cat["profiles"]) == 4
    assert cat["default"] is None


def test_profile_catalog_fields() -> None:
    cat = profile_catalog()
    for row in cat["profiles"]:
        assert "id" in row
        assert "description" in row
        assert "flags" in row
        assert isinstance(row["flags"], dict)


def test_profile_catalog_active_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_RUN_PROFILE", "autonomous")
    cat = profile_catalog()
    assert cat["active"] == "autonomous"
    assert cat["default"] == "autonomous"
