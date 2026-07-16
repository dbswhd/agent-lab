"""CX8 (09-context-engineering.md §11) — src/agent_lab/context/bundle_recipe.py.

This is a standalone slice, NOT wired into build_context_bundle's live
per-turn path -- these tests exercise it directly, not through bundle.py.
Covers: mission-phase -> ActivityKind mapping (including the documented
gaps), and build_manifest_via_recipe's happy path for the activities its
current adapter coverage can satisfy (CLARIFY/PLAN/EXECUTE), plus the
documented EVIDENCE gap for CRITIC/REPAIR/SCRIBE.
"""

from __future__ import annotations

import pytest

from agent_lab.context.bundle_recipe import (
    RecipeBundleInputs,
    activity_kind_for_mission_phase,
    build_manifest_via_recipe,
)
from agent_lab.context.recipe import ActivityKind, ContextSelectionError, SourceClass
from agent_lab.wisdom.playbook import PlaybookBullet


@pytest.mark.parametrize(
    "phase,expected",
    [
        ("CLARIFY", ActivityKind.CLARIFY),
        ("DISCUSS", ActivityKind.PLAN),
        ("PLAN_GATE", ActivityKind.PLAN),
        ("PLAN_REJECT", ActivityKind.PLAN),
        ("EXECUTE_QUEUE", ActivityKind.EXECUTE),
        ("DRY_RUN", ActivityKind.EXECUTE),
        ("MERGE_REVIEW", ActivityKind.CRITIC),
        ("VERIFY", ActivityKind.CRITIC),
        ("REPAIR", ActivityKind.REPAIR),
    ],
)
def test_activity_kind_for_mission_phase_maps_known_phases(phase: str, expected: ActivityKind) -> None:
    assert activity_kind_for_mission_phase(phase) == expected


@pytest.mark.parametrize("phase", ["MISSION_DEFINE", "MISSION_PAUSED", "MISSION_DONE", "", "not-a-real-phase"])
def test_activity_kind_for_mission_phase_returns_none_for_unmapped_phases(phase: str) -> None:
    """No ActivityKind for bootstrap/paused/terminal states or anything
    unrecognized -- callers must treat None as 'fall back to legacy bundle.py'."""
    assert activity_kind_for_mission_phase(phase) is None


def _full_inputs() -> RecipeBundleInputs:
    return RecipeBundleInputs(
        plan_md="# Plan\n\nship the feature",
        session_guidance="[PLATFORM.md]\nfollow the rules",
        clarify_facts=[{"id": "q1", "answer": "use React", "at": "2026-07-16T00:00:00Z"}],
        goal_ledger=[{"event": "plan approved", "phase": "plan"}],
        repo_tree="[Repo tree] `/repo`\n- src/",
        agents_md_hierarchy="repo-specific AGENTS.md guidance",
        reply_policy_guidance_parts=["respond concisely", "cite sources"],
    )


def test_build_manifest_via_recipe_satisfies_clarify() -> None:
    manifest = build_manifest_via_recipe(ActivityKind.CLARIFY, _full_inputs())
    included_sources = {item.source for item in manifest.included}
    assert SourceClass.SYSTEM_INVARIANT in included_sources
    assert SourceClass.HUMAN_INTENT in included_sources
    assert SourceClass.PROJECT_DOC in included_sources
    assert SourceClass.RUNTIME_STATE in included_sources


def test_build_manifest_via_recipe_satisfies_plan() -> None:
    manifest = build_manifest_via_recipe(ActivityKind.PLAN, _full_inputs())
    included_sources = {item.source for item in manifest.included}
    assert SourceClass.HUMAN_INTENT in included_sources
    assert SourceClass.SYSTEM_INVARIANT in included_sources
    assert SourceClass.REPO_CONTEXT in included_sources
    assert SourceClass.PROJECT_DOC in included_sources
    assert SourceClass.RUNTIME_STATE in included_sources


def test_build_manifest_via_recipe_satisfies_execute() -> None:
    manifest = build_manifest_via_recipe(ActivityKind.EXECUTE, _full_inputs())
    included_sources = {item.source for item in manifest.included}
    assert SourceClass.APPROVED_PLAN in included_sources
    assert SourceClass.SYSTEM_INVARIANT in included_sources
    assert SourceClass.RUNTIME_STATE in included_sources
    assert SourceClass.REPO_CONTEXT in included_sources


@pytest.mark.parametrize("activity", [ActivityKind.CRITIC, ActivityKind.REPAIR, ActivityKind.SCRIBE])
def test_build_manifest_via_recipe_raises_missing_evidence_for_unadapted_activities(activity: ActivityKind) -> None:
    """Documented gap: no adapter exists yet for SourceClass.EVIDENCE, so
    every recipe requiring it (CRITIC/REPAIR/SCRIBE) must fail closed here,
    not silently produce an incomplete manifest."""
    with pytest.raises(ContextSelectionError, match="missing required sources"):
        build_manifest_via_recipe(activity, _full_inputs())


def test_build_manifest_via_recipe_excludes_semantic_memory_items_for_plan_as_not_allowed() -> None:
    """PLAN_RECIPE's optional_sources is {EPISODE, EXTERNAL_CONTENT,
    AGENT_OPINION} -- it does NOT include SEMANTIC_MEMORY, so wisdom-index/
    playbook items (both SEMANTIC_MEMORY) are correctly excluded as
    "not_allowed", not included. This documents a real current limitation:
    none of the three activities this slice can currently satisfy
    (CLARIFY/PLAN/EXECUTE) allow SEMANTIC_MEMORY in their recipe, so wisdom/
    playbook adapters, while wired here, have no activity to demonstrate
    inclusion through yet -- REPAIR's recipe allows SEMANTIC_MEMORY but
    can't build a manifest at all (see the EVIDENCE-gap test above)."""
    inputs = RecipeBundleInputs(
        plan_md="# Plan\n\nship it",
        session_guidance="guidance text",
        clarify_facts=[{"id": "q1", "answer": "fact", "at": "2026-07-16"}],
        repo_tree="[Repo tree]\n- src/",
        agents_md_hierarchy="hierarchy guidance",
        reply_policy_guidance_parts=["be concise"],
        wisdom_index_hits=[{"id": "doc-1", "snippet": "relevant note", "score": 2.0}],
        playbook_bullets=[
            PlaybookBullet(
                id="b1", description="always verify first", pattern_id="p1",
                evidence_count=2, status="active", harness_rev="rev1", updated_at="2026-07-15",
            ),
        ],
    )
    manifest = build_manifest_via_recipe(ActivityKind.PLAN, inputs)
    excluded = dict(manifest.excluded)
    assert excluded.get("wisdom_index:doc-1") == "not_allowed"
    assert excluded.get("playbook:b1") == "not_allowed"


def test_build_manifest_via_recipe_empty_inputs_reports_missing_required_sources() -> None:
    with pytest.raises(ContextSelectionError, match="missing required sources"):
        build_manifest_via_recipe(ActivityKind.PLAN, RecipeBundleInputs())
