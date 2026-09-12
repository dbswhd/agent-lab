"""B1–B2 — core flag tier guard."""

from __future__ import annotations

from agent_lab.runtime_flags import FLAG_REGISTRY

# SSOT: docs/FLAG-TIERS-DRAFT.md § Tier 1 — Core 15
CORE_FEATURE_FLAGS: tuple[str, ...] = (
    "AGENT_LAB_RUN_PROFILE",
    "AGENT_LAB_ORACLE_LIVE",
    "AGENT_LAB_PLAN_WORKFLOW",
    "AGENT_LAB_EXECUTE_INBOX",
    "AGENT_LAB_MISSION_AUTHORITY",
    "AGENT_LAB_EXTERNAL_TOOLS",
    "AGENT_LAB_TURN_METRICS",
    "AGENT_LAB_OUTCOME_LEDGER",
    "AGENT_LAB_FEEDBACK_ADVISOR",
    "AGENT_LAB_PLAN_FSM_SKILL_FIRST",
    "AGENT_LAB_PLAN_PHASE_PROJECTION",
    "AGENT_LAB_PLAN_SCRIBE_REPAIR",
    "AGENT_LAB_CORRECTION_HARVESTER",
    "AGENT_LAB_REPO_MAP",
    "AGENT_LAB_COMPACT_TOOL_OUTPUT",
)


def test_core_tier_has_exactly_fifteen_flags() -> None:
    assert len(CORE_FEATURE_FLAGS) == 15
    assert len(set(CORE_FEATURE_FLAGS)) == 15


def test_core_flags_registered_as_feature() -> None:
    registry = {row.name: row for row in FLAG_REGISTRY}
    missing = [name for name in CORE_FEATURE_FLAGS if name not in registry]
    assert not missing, f"core flags missing from FLAG_REGISTRY: {missing}"
    non_feature = [name for name in CORE_FEATURE_FLAGS if registry[name].category != "feature"]
    assert not non_feature, f"core flags must be category=feature: {non_feature}"


def test_balanced_profile_owns_all_core_flags() -> None:
    from agent_lab.run.profile import _PROFILE_CONFIGS

    balanced = _PROFILE_CONFIGS["balanced"]
    owned = balanced.owned_flags()
    missing = [name for name in CORE_FEATURE_FLAGS if name not in owned]
    assert not missing, f"balanced profile must own core flags: {missing}"
