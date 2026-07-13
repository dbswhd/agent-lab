"""Tests for Run Profile System (P1-6)."""

from __future__ import annotations

import os

import pytest

from agent_lab.run.profile import (
    RunProfileConfig,
    apply_run_profile,
    default_run_profile,
    feature_flags_without_owner,
    flag_profile_membership,
    list_profiles,
    profile_catalog,
    profile_ids,
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
    assert default_run_profile() == "balanced"


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
    assert cfg.flags.get("AGENT_LAB_ROOM_PRESET") == "supervisor"


def test_balanced_profile_uses_supervisor_preset() -> None:
    cfg = resolve_profile("balanced")
    assert cfg is not None
    assert cfg.flags.get("AGENT_LAB_ROOM_PRESET") == "supervisor"


def test_balanced_profile_has_s1_feedback_flags() -> None:
    cfg = resolve_profile("balanced")
    assert cfg is not None
    assert cfg.flags.get("AGENT_LAB_TURN_METRICS") == "1"
    assert cfg.flags.get("AGENT_LAB_OUTCOME_LEDGER") == "1"
    assert cfg.flags.get("AGENT_LAB_FEEDBACK_ADVISOR") == "1"


def test_supervisor_profiles_default_plan_write_authority_on() -> None:
    """Slice 1–3: authority defaults on; still no-op without DUAL_WRITE."""
    for name in ("balanced", "thorough", "autonomous"):
        cfg = resolve_profile(name)
        assert cfg is not None
        assert cfg.flags.get("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY") == "1"
        assert cfg.flags.get("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY") == "1"
        assert cfg.flags.get("AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY") == "1"
    fast = resolve_profile("fast")
    assert fast is not None
    assert "AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY" not in fast.flags
    assert "AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY" not in fast.flags
    assert "AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY" not in fast.flags


def test_thorough_profile_uses_supervisor_preset() -> None:
    cfg = resolve_profile("thorough")
    assert cfg is not None
    assert cfg.flags.get("AGENT_LAB_ROOM_PRESET") == "supervisor"


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
    assert cat["default"] == "balanced"


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


def test_all_profile_flags_are_registered() -> None:
    """N2: every profile-owned flag must exist in FLAG_REGISTRY."""
    from agent_lab.runtime_flags import FLAG_REGISTRY

    registered = {row.name for row in FLAG_REGISTRY}
    missing: list[str] = []
    for cfg in list_profiles():
        for name in cfg.owned_flags():
            if name not in registered:
                missing.append(f"{cfg.profile}:{name}")
    assert not missing, f"Profile flags missing from FLAG_REGISTRY: {missing}"


def test_four_profiles_mapped() -> None:
    """N2 gauge: 4/4 profiles present with non-empty ownership."""
    assert profile_ids() == _ALL_PROFILES
    membership = flag_profile_membership()
    assert membership
    for profile in _ALL_PROFILES:
        owned = [name for name, owners in membership.items() if profile in owners]
        assert owned, f"profile {profile} owns no flags"


def test_f2_every_feature_flag_has_owner() -> None:
    """F2: every feature flag is owned by ≥1 profile (no balanced fallback)."""
    from agent_lab.runtime_flags import FLAG_REGISTRY

    fallback = feature_flags_without_owner()
    assert fallback == [], f"Feature flags missing explicit owner: {fallback}"

    membership = flag_profile_membership()
    feature_names = {row.name for row in FLAG_REGISTRY if row.category == "feature"}
    assert feature_names
    for name in feature_names:
        assert membership.get(name), f"{name} has no profile owner"


def test_f2_ownership_spread_across_profiles() -> None:
    """F2: ownership is not dumped only on balanced."""
    counts = {pid: 0 for pid in _ALL_PROFILES}
    for cfg in list_profiles():
        counts[cfg.profile] = len(cfg.owned_flags())
    assert counts["fast"] >= 20
    assert counts["thorough"] >= 20
    assert counts["autonomous"] >= 15
    assert counts["balanced"] >= 40


def test_apply_run_profile_ignores_owns_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Membership-only owns must not force env values."""
    monkeypatch.delenv("AGENT_LAB_EFFICIENCY", raising=False)
    apply_run_profile("fast")
    assert os.environ.get("AGENT_LAB_EFFICIENCY") is None


def test_flags_payload_includes_profile_membership() -> None:
    from agent_lab.runtime_flags import build_flags_payload

    payload = build_flags_payload()
    assert payload["profiles"] == list(_ALL_PROFILES)
    assert payload["active_profile"] in {*_ALL_PROFILES, None}
    room_preset = next(row for row in payload["flags"] if row["name"] == "AGENT_LAB_ROOM_PRESET")
    assert set(room_preset["profiles"]) == {
        "fast",
        "balanced",
        "thorough",
        "autonomous",
    }
    efficiency = next(row for row in payload["flags"] if row["name"] == "AGENT_LAB_EFFICIENCY")
    assert "fast" in efficiency["profiles"]


def test_flags_payload_profile_filter() -> None:
    from agent_lab.runtime_flags import build_flags_payload

    payload = build_flags_payload(profile="fast")
    assert payload["profile_filter"] == "fast"
    assert payload["flags"]
    assert all("fast" in (row.get("profiles") or []) for row in payload["flags"])
    # owns-only flags appear in filter
    names = {row["name"] for row in payload["flags"]}
    assert "AGENT_LAB_EFFICIENCY" in names
