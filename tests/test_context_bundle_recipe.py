"""CX8 (09-context-engineering.md §11) — src/agent_lab/context/bundle_recipe.py.

This is a standalone slice, NOT wired into build_context_bundle's live
per-turn path -- these tests exercise it directly, not through bundle.py.
Covers: mission-phase -> ActivityKind mapping (including the documented
gaps), and build_manifest_via_recipe's happy path for all six activities
now that adapt_artifacts closes the EVIDENCE gap (2026-07-16) -- plus a
regression guard confirming CRITIC/REPAIR/SCRIBE still fail closed, exactly
as before, when the caller doesn't supply artifacts.
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
        artifacts=[
            {
                "id": "art-1",
                "summary": "ran the test suite, all green",
                "ts": "2026-07-16T00:00:02Z",
                "path": "artifacts/art-1.txt",
            },
        ],
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
def test_build_manifest_via_recipe_satisfies_evidence_requiring_activities(activity: ActivityKind) -> None:
    """2026-07-16 — adapt_artifacts closed the EVIDENCE gap: CRITIC/REPAIR/
    SCRIBE (the three recipes requiring EVIDENCE) can now build a manifest
    given artifacts input, where previously they always raised."""
    manifest = build_manifest_via_recipe(activity, _full_inputs())
    included_sources = {item.source for item in manifest.included}
    assert SourceClass.EVIDENCE in included_sources
    assert SourceClass.SYSTEM_INVARIANT in included_sources


@pytest.mark.parametrize("activity", [ActivityKind.CRITIC, ActivityKind.REPAIR, ActivityKind.SCRIBE])
def test_build_manifest_via_recipe_still_raises_without_artifacts_input(activity: ActivityKind) -> None:
    """Regression guard: the gap isn't papered over by a default -- a caller
    that doesn't supply `artifacts` still gets the same fail-closed
    behavior as before adapt_artifacts existed."""
    inputs = RecipeBundleInputs(
        plan_md="# Plan\n\nship the feature",
        session_guidance="[PLATFORM.md]\nfollow the rules",
        clarify_facts=[{"id": "q1", "answer": "use React", "at": "2026-07-16T00:00:00Z"}],
        reply_policy_guidance_parts=["respond concisely"],
    )
    with pytest.raises(ContextSelectionError, match="missing required sources"):
        build_manifest_via_recipe(activity, inputs)


def test_build_manifest_via_recipe_excludes_semantic_memory_items_for_plan_as_not_allowed() -> None:
    """PLAN_RECIPE's optional_sources is {EPISODE, EXTERNAL_CONTENT,
    AGENT_OPINION} -- it does NOT include SEMANTIC_MEMORY, so wisdom-index/
    playbook items (both SEMANTIC_MEMORY) are correctly excluded as
    "not_allowed" for PLAN specifically (see the REPAIR test below, which
    DOES allow SEMANTIC_MEMORY and includes them)."""
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
                id="b1",
                description="always verify first",
                pattern_id="p1",
                evidence_count=2,
                status="active",
                harness_rev="rev1",
                updated_at="2026-07-15",
            ),
        ],
    )
    manifest = build_manifest_via_recipe(ActivityKind.PLAN, inputs)
    excluded = dict(manifest.excluded)
    assert excluded.get("wisdom_index:doc-1") == "not_allowed"
    assert excluded.get("playbook:b1") == "not_allowed"


def test_build_manifest_via_recipe_includes_semantic_memory_items_for_repair() -> None:
    """REPAIR_RECIPE's optional_sources DOES include SEMANTIC_MEMORY --
    now that adapt_artifacts satisfies REPAIR's EVIDENCE requirement, this
    is the first activity in this slice that can actually demonstrate
    wisdom/playbook items being included, not just excluded."""
    inputs = RecipeBundleInputs(
        plan_md="# Plan\n\nfix the regression",
        reply_policy_guidance_parts=["be concise"],
        clarify_facts=[{"id": "q1", "answer": "root cause found", "at": "2026-07-16"}],
        artifacts=[{"id": "art-1", "summary": "failing test output", "ts": "2026-07-16"}],
        wisdom_index_hits=[{"id": "doc-1", "snippet": "similar past fix", "score": 2.0}],
        playbook_bullets=[
            PlaybookBullet(
                id="b1",
                description="check for off-by-one first",
                pattern_id="p1",
                evidence_count=2,
                status="active",
                harness_rev="rev1",
                updated_at="2026-07-15",
            ),
        ],
    )
    manifest = build_manifest_via_recipe(ActivityKind.REPAIR, inputs)
    included_ids = {item.item_id for item in manifest.included}
    assert "wisdom_index:doc-1" in included_ids
    assert "playbook:b1" in included_ids


def test_build_manifest_via_recipe_empty_inputs_reports_missing_required_sources() -> None:
    with pytest.raises(ContextSelectionError, match="missing required sources"):
        build_manifest_via_recipe(ActivityKind.PLAN, RecipeBundleInputs())


def test_build_manifest_via_recipe_wires_the_14_newly_adapted_blocks() -> None:
    """2026-07-16 -- the 14 producers previously assumed to be un-adaptable
    bundle.py internals (they're actually standalone functions in their own
    modules) are now wired through RecipeBundleInputs. PLAN_RECIPE's
    optional_sources includes AGENT_OPINION, so this is the activity that
    can actually demonstrate mailbox/peer/turn_bridge inclusion, not just
    exclusion."""
    inputs = RecipeBundleInputs(
        plan_md="# Plan\n\nship it",
        session_guidance="guidance text",
        clarify_facts=[{"id": "q1", "answer": "fact", "at": "2026-07-16"}],
        repo_tree="[Repo tree]\n- src/",
        agents_md_hierarchy="repo-specific AGENTS.md guidance",
        reply_policy_guidance_parts=["be concise"],
        team_task_block="[팀 작업 보드]\n- [pending] fix bug (@codex)",
        objection_block="[미해결 이의]\n- codex BLOCK -> task-1: needs review",
        challenge_owner_block="[challenge owner]\n- task-1 owner must respond",
        plugin_allowlist_block="[claude plugins]\n- allowed: web-search",
        capability_preamble="[capabilities]\n- can run shell commands",
        thread_resume_block="[Agent thread resume]\ncontinuing from prior session",
        dispatch_intent_block="[dispatch intents]\n- lead -> codex: investigate",
        plan_open_block="[plan 미결]\n- open item 1",
        turn_state_block="[턴 blackboard]\nanchor: claude R1",
        turn_bridge_block="[R1 요약 · bridge]\n- codex: found the issue",
        peer_block="[이번 턴 · 동료 발화]\ncodex: I think we should refactor this",
        envelope_follow_up_block="Respond using the MESSAGE envelope format.",
        agent_tool_rules_block="[tool rules]\n- shell access granted this turn",
        mailbox_messages=[{"id": "mail-1", "from": "codex", "body": "check the logs", "ts": "2026-07-16"}],
    )

    manifest = build_manifest_via_recipe(ActivityKind.PLAN, inputs)

    included_ids = {item.item_id for item in manifest.included}
    assert "team_task_block" in included_ids
    assert "objection_block" in included_ids
    assert "challenge_owner_block" in included_ids
    assert "plugin_allowlist_block" in included_ids
    assert "capability_preamble" in included_ids
    assert "thread_resume_block" in included_ids
    assert "dispatch_intent_block" in included_ids
    assert "plan_open_block" in included_ids
    assert "turn_state_block" in included_ids
    assert "turn_bridge_block" in included_ids
    assert "peer_block" in included_ids
    assert "envelope_follow_up_block" in included_ids
    assert "agent_tool_rules_block" in included_ids
    assert "mailbox:mail-1" in included_ids


def test_build_manifest_via_recipe_session_skills_block_is_forbidden_for_execute() -> None:
    """adapt_session_skills_block maps to EPISODE, which EXECUTE_RECIPE
    explicitly forbids (a session-skill item shouldn't smuggle unreviewed
    mission-scoped learning into an execute turn)."""
    inputs = RecipeBundleInputs(
        plan_md="# Plan\n\nship it",
        reply_policy_guidance_parts=["be concise"],
        clarify_facts=[{"id": "q1", "answer": "fact", "at": "2026-07-16"}],
        repo_tree="[Repo tree]\n- src/",
        session_skills_block="## Session skills\n- use the new helper",
    )
    manifest = build_manifest_via_recipe(ActivityKind.EXECUTE, inputs)
    excluded = dict(manifest.excluded)
    assert excluded.get("session_skills_block") == "forbidden"


def test_build_manifest_via_recipe_wires_recent_messages_by_role() -> None:
    """2026-07-16 -- the recent conversation transcript, previously left
    as a genuine taxonomy gap, is now decomposed per-message by role. PLAN
    is used since its optional_sources includes AGENT_OPINION (the peer
    reply's mapping)."""
    inputs = RecipeBundleInputs(
        plan_md="# Plan\n\nship it",
        session_guidance="guidance text",
        clarify_facts=[{"id": "q1", "answer": "fact", "at": "2026-07-16"}],
        repo_tree="[Repo tree]\n- src/",
        agents_md_hierarchy="repo-specific AGENTS.md guidance",
        reply_policy_guidance_parts=["be concise"],
        self_agent="claude",
        recent_messages=[
            {"role": "user", "content": "please add tests", "ts": "2026-07-16T00:00:00Z"},
            {"role": "agent", "agent": "claude", "content": "adding tests now", "ts": "2026-07-16T00:00:01Z"},
            {"role": "agent", "agent": "codex", "content": "I already started on this", "ts": "2026-07-16T00:00:02Z"},
        ],
    )
    manifest = build_manifest_via_recipe(ActivityKind.PLAN, inputs)
    by_id = {item.item_id: item for item in manifest.included}
    # recent:0 (Human) is HUMAN_INTENT, a PLAN_RECIPE required source.
    assert by_id["recent:0"].source == SourceClass.HUMAN_INTENT
    # recent:1 (claude's own reply) is EPISODE, recent:2 (codex's reply) is
    # AGENT_OPINION -- both are in PLAN_RECIPE's optional_sources, so both
    # survive selection rather than one being silently excluded.
    assert by_id["recent:1"].source == SourceClass.EPISODE
    assert by_id["recent:2"].source == SourceClass.AGENT_OPINION


def test_build_manifest_via_recipe_satisfies_project_doc_via_project_md_alone() -> None:
    """2026-07-16 -- PROJECT.md/AGENTS.md-flat/SHARED_CONTEXT.md were never
    wired into RecipeBundleInputs at all (only agents_md_hierarchy was),
    which meant PROJECT_DOC coverage silently depended on plan_md
    containing file-path hints for the hierarchy chain to resolve anything.
    A caller with an empty/hint-free plan_md but real PROJECT.md content
    should still satisfy PROJECT_DOC-requiring recipes (CLARIFY/PLAN)."""
    inputs = RecipeBundleInputs(
        plan_md="",
        session_guidance="guidance text",
        clarify_facts=[{"id": "q1", "answer": "fact", "at": "2026-07-16"}],
        reply_policy_guidance_parts=["be concise"],
        project_md="# Project\n\nthis is the project",
    )
    manifest = build_manifest_via_recipe(ActivityKind.CLARIFY, inputs)
    included_ids = {item.item_id for item in manifest.included}
    assert "project_md" in included_ids


def test_build_manifest_via_recipe_wires_agents_md_flat_and_shared_context_md() -> None:
    inputs = RecipeBundleInputs(
        plan_md="# Plan\n\nship it",
        session_guidance="guidance text",
        clarify_facts=[{"id": "q1", "answer": "fact", "at": "2026-07-16"}],
        repo_tree="[Repo tree]\n- src/",
        reply_policy_guidance_parts=["be concise"],
        agents_md_flat="flat AGENTS.md guidance",
        shared_context_md="shared context body",
    )
    manifest = build_manifest_via_recipe(ActivityKind.PLAN, inputs)
    included_ids = {item.item_id for item in manifest.included}
    assert "agents_md_flat" in included_ids
    assert "shared_context_md" in included_ids
