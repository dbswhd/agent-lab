from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agent_lab.model_policy import (
    ModelProfile,
    agent_model_profiles,
    agents_within_cost_tier,
    loop_blockers,
    loop_readiness_failure,
    loop_ready,
    model_profile_for,
    model_readiness,
    preferred_cost_tier_for_category,
    register_model_profile,
    resolve_runtime_model_id,
    team_ready,
)
from agent_lab.trust_budget import budget_agent_tier_cap


def test_default_agent_model_profiles_are_team_ready() -> None:
    profiles = agent_model_profiles()
    assert set(profiles) == {"cursor", "codex", "claude"}
    assert all(team_ready(profile) for profile in profiles.values())


def test_default_agent_profiles_are_loop_ready() -> None:
    profiles = agent_model_profiles()
    assert all(loop_ready(profile) for profile in profiles.values())


def test_loop_ready_requires_tools_inbox_and_envelope() -> None:
    base = agent_model_profiles()["cursor"]
    assert loop_ready(base) is True

    assert loop_blockers(replace(base, supports_tools=False)) == ("supports_tools",)
    assert loop_blockers(replace(base, supports_inbox_mcp=False)) == ("supports_inbox_mcp",)
    assert loop_blockers(replace(base, supports_json_envelope=False)) == ("supports_json_envelope",)
    assert loop_ready(replace(base, supports_tools=False)) is False


def test_model_id_lookup_env_and_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
    readiness = model_readiness("cursor", model_id="llama-3-local")
    assert readiness is not None
    assert readiness.team_ready is True
    assert readiness.loop_ready is False

    monkeypatch.setenv("CURSOR_MODEL", "custom-cursor-model")
    assert resolve_runtime_model_id("cursor") == "custom-cursor-model"
    assert model_profile_for("cursor").model_id == "custom-cursor-model"

    import agent_lab.model_policy as model_policy_mod

    registry_before = dict(model_policy_mod._MODEL_PROFILE_REGISTRY)
    monkeypatch.setenv("CURSOR_MODEL", "llama-3-local")
    try:
        register_model_profile(
            ModelProfile(
                provider="local",
                model_id="llama-3-local",
                agent="cursor",
                supports_tools=True,
                supports_inbox_mcp=True,
                supports_json_envelope=True,
                supports_long_context=False,
                cost_tier="low",
                latency_tier="high",
            )
        )
        assert model_readiness("cursor").loop_ready is True
        assert loop_readiness_failure(["cursor"]) is None
    finally:
        model_policy_mod._MODEL_PROFILE_REGISTRY.clear()
        model_policy_mod._MODEL_PROFILE_REGISTRY.update(registry_before)

    monkeypatch.setenv("AGENT_LAB_LOOP_MAX_COST_TIER", "medium")
    monkeypatch.setenv("CODEX_MODEL", "expensive-model")
    base_codex = model_policy_mod.agent_model_profiles()["codex"]
    try:
        model_policy_mod.register_model_profile(replace(base_codex, model_id="expensive-model", cost_tier="high"))
        cost_failure = model_policy_mod.loop_readiness_failure(["codex"])
        assert cost_failure is not None
        assert "cost tier" in cost_failure.reason
    finally:
        model_policy_mod._MODEL_PROFILE_REGISTRY.clear()
        model_policy_mod._MODEL_PROFILE_REGISTRY.update(registry_before)


def test_preferred_cost_tier_for_category() -> None:
    assert preferred_cost_tier_for_category("quick") == "low"
    assert preferred_cost_tier_for_category("standard") is None
    assert preferred_cost_tier_for_category("deep") is None
    assert preferred_cost_tier_for_category("critical") is None


def test_agents_within_cost_tier_filters_high_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
    # cursor=low, codex=high, claude=high — only cursor survives "low" cap
    result = agents_within_cost_tier(["cursor", "codex", "claude"], "low")
    assert result == ["cursor"]


def test_agents_within_cost_tier_medium_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
    # medium cap: low+medium pass, high blocked
    # cursor=low passes, codex=high blocked, claude=high blocked
    result = agents_within_cost_tier(["cursor", "codex", "claude"], "medium")
    assert "cursor" in result
    assert "codex" not in result
    assert "claude" not in result


def test_agents_within_cost_tier_fallback_when_all_filtered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
    # All high-cost agents: filtering "low" would remove all → fallback to original
    result = agents_within_cost_tier(["codex", "claude"], "low")
    assert result == ["codex", "claude"]


def test_budget_agent_tier_cap_no_budget() -> None:
    # total==0 means no budget configured → no constraint
    assert budget_agent_tier_cap(None) is None
    assert budget_agent_tier_cap({}) is None
    assert budget_agent_tier_cap({"trust_budget": {"auto_merge_total": 0, "auto_merge_remaining": 0}}) is None


def test_budget_agent_tier_cap_exhausted() -> None:
    run_meta = {"trust_budget": {"auto_merge_total": 10, "auto_merge_remaining": 0}}
    assert budget_agent_tier_cap(run_meta) == "low"


def test_budget_agent_tier_cap_low_remaining() -> None:
    # ≤25% remaining → "medium"
    run_meta = {"trust_budget": {"auto_merge_total": 10, "auto_merge_remaining": 2}}
    assert budget_agent_tier_cap(run_meta) == "medium"

    run_meta2 = {"trust_budget": {"auto_merge_total": 10, "auto_merge_remaining": 1}}
    assert budget_agent_tier_cap(run_meta2) == "medium"


def test_budget_agent_tier_cap_healthy_budget() -> None:
    # >25% remaining → no constraint
    run_meta = {"trust_budget": {"auto_merge_total": 10, "auto_merge_remaining": 5}}
    assert budget_agent_tier_cap(run_meta) is None

    run_meta2 = {"trust_budget": {"auto_merge_total": 10, "auto_merge_remaining": 3}}
    assert budget_agent_tier_cap(run_meta2) is None


def test_load_loop_eval_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.model_policy as model_policy_mod

    eval_path = tmp_path / "loop_model_eval.json"
    eval_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "agent": "cursor",
                        "model_id": "oss-eval-pass",
                        "provider": "local",
                        "supports_tools": True,
                        "supports_inbox_mcp": True,
                        "supports_json_envelope": True,
                        "supports_long_context": False,
                        "cost_tier": "low",
                        "latency_tier": "high",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_LOOP_EVAL_REGISTRY", str(eval_path))
    registry_before = dict(model_policy_mod._MODEL_PROFILE_REGISTRY)
    model_policy_mod._LOOP_EVAL_LOADED = False
    try:
        loaded = model_policy_mod.load_loop_eval_registry(force=True)
        assert loaded == 1
        readiness = model_policy_mod.model_readiness("cursor", model_id="oss-eval-pass")
        assert readiness is not None
        assert readiness.loop_ready is True
    finally:
        model_policy_mod._LOOP_EVAL_LOADED = False
        model_policy_mod._MODEL_PROFILE_REGISTRY.clear()
        model_policy_mod._MODEL_PROFILE_REGISTRY.update(registry_before)
