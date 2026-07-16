"""CX1/CX8 (09-context-engineering.md §11) — producer → ContextItem adapters.

`src/agent_lab/context/adapters.py` is the first thing that actually feeds
`select_context()` (previously exercised only with synthetic ContextItems).
One test group per adapter, covering: normal conversion, empty/no-content
input returning None/[] (matching each producer's own "nothing to
contribute" convention), and the item_id/SourceClass/freshness mapping the
CX1 source registry specifies for that producer.
"""

from __future__ import annotations

from agent_lab.context.adapters import (
    adapt_agents_md_flat,
    adapt_agents_md_hierarchy,
    adapt_approved_plan,
    adapt_clarify_facts,
    adapt_goal_ledger,
    adapt_mission_notepad,
    adapt_playbook_bullets,
    adapt_project_md,
    adapt_reply_policy_guidance,
    adapt_repo_tree,
    adapt_session_guidance,
    adapt_shared_context_md,
    adapt_steer_queue,
    adapt_wisdom_entries,
    adapt_wisdom_index_hits,
)
from agent_lab.context.recipe import ActivityKind, ContextItem, ContextNeed, SourceClass, select_context
from agent_lab.wisdom.playbook import PlaybookBullet
from agent_lab.wisdom.store import WisdomEntry


def test_adapt_project_md_maps_to_project_doc_with_mtime_freshness() -> None:
    item = adapt_project_md("# Project\n\nsome content", mtime=1700000000.0)
    assert item is not None
    assert item.source == SourceClass.PROJECT_DOC
    assert item.item_id == "project_md"
    assert item.freshness == "1700000000.0"
    assert item.content == "# Project\n\nsome content"


def test_adapt_project_md_returns_none_for_empty_content() -> None:
    assert adapt_project_md("") is None
    assert adapt_project_md("   \n  ") is None


def test_adapt_agents_md_flat_and_hierarchy_use_distinct_item_ids_no_shared_conflict_key() -> None:
    """CX1 §2 left flat-vs-hierarchy dedup as an open CX2/CX8 decision — the
    adapter must not force it by giving them a shared conflict_key."""
    flat = adapt_agents_md_flat("flat guide")
    hierarchy = adapt_agents_md_hierarchy("hierarchy guide")
    assert flat is not None and hierarchy is not None
    assert flat.item_id != hierarchy.item_id
    assert flat.conflict_key is None
    assert hierarchy.conflict_key is None
    assert flat.source == hierarchy.source == SourceClass.PROJECT_DOC


def test_adapt_approved_plan_maps_to_approved_plan_source() -> None:
    item = adapt_approved_plan("# Plan\n\nship it")
    assert item is not None
    assert item.item_id == "approved_plan"
    assert item.source == SourceClass.APPROVED_PLAN
    assert item.provenance == "plan.md"


def test_adapt_approved_plan_returns_none_for_empty_plan() -> None:
    assert adapt_approved_plan("") is None
    assert adapt_approved_plan("   ") is None


def test_adapt_shared_context_md_maps_to_project_doc() -> None:
    item = adapt_shared_context_md("shared context body")
    assert item is not None
    assert item.source == SourceClass.PROJECT_DOC
    assert item.item_id == "shared_context_md"


def test_adapt_repo_tree_uses_commit_sha_as_freshness_when_given() -> None:
    item = adapt_repo_tree("[Repo tree] `/repo`\n- src/", commit_sha="abc123")
    assert item is not None
    assert item.source == SourceClass.REPO_CONTEXT
    assert item.freshness == "abc123"


def test_adapt_repo_tree_without_commit_sha_leaves_freshness_none() -> None:
    item = adapt_repo_tree("[Repo tree] `/repo`\n- src/")
    assert item is not None
    assert item.freshness is None


def test_adapt_session_guidance_maps_to_human_intent() -> None:
    item = adapt_session_guidance("[PLATFORM.md — agent protocol]\nsome guidance")
    assert item is not None
    assert item.source == SourceClass.HUMAN_INTENT


def test_adapt_reply_policy_guidance_produces_one_item_per_part() -> None:
    parts = ["response contract guidance", "dispatch lead guidance", ""]
    items = adapt_reply_policy_guidance(parts)
    # empty part skipped
    assert [item.content for item in items] == ["response contract guidance", "dispatch lead guidance"]
    assert all(item.source == SourceClass.SYSTEM_INVARIANT for item in items)
    assert [item.item_id for item in items] == ["guidance_part:0", "guidance_part:1"]


def test_adapt_mission_notepad_scopes_item_id_by_session() -> None:
    item = adapt_mission_notepad("notepad tail text", session_id="sess-42")
    assert item is not None
    assert item.item_id == "mission_notepad:sess-42"
    assert item.source == SourceClass.EPISODE


def test_adapt_steer_queue_skips_entries_without_text_or_id() -> None:
    entries = [
        {"id": "steer_1", "text": "do the thing", "ts": "2026-07-16T00:00:00Z", "target": "any"},
        {"id": "", "text": "no id, dropped", "ts": "2026-07-16T00:00:01Z"},
        {"id": "steer_2", "text": "  ", "ts": "2026-07-16T00:00:02Z"},
    ]
    items = adapt_steer_queue(entries)
    assert len(items) == 1
    assert items[0].item_id == "steer:steer_1"
    assert items[0].source == SourceClass.HUMAN_INTENT
    assert items[0].freshness == "2026-07-16T00:00:00Z"


def test_adapt_wisdom_index_hits_uses_score_as_relevance() -> None:
    hits = [
        {"id": "doc-1", "snippet": "relevant text", "score": 3.7, "at": "2026-07-01", "path": "notes.md"},
        {"id": "", "snippet": "no id, dropped", "score": 5.0},
    ]
    items = adapt_wisdom_index_hits(hits)
    assert len(items) == 1
    assert items[0].item_id == "wisdom_index:doc-1"
    assert items[0].relevance == 4  # round(3.7)
    assert items[0].source == SourceClass.SEMANTIC_MEMORY
    assert items[0].freshness == "2026-07-01"


def test_adapt_playbook_bullets_maps_to_semantic_memory_with_freshness() -> None:
    bullets = [
        PlaybookBullet(
            id="b1", description="always run tests first", pattern_id="p1",
            evidence_count=3, status="active", harness_rev="rev1", updated_at="2026-07-10",
        ),
    ]
    items = adapt_playbook_bullets(bullets)
    assert len(items) == 1
    assert items[0].item_id == "playbook:b1"
    assert items[0].source == SourceClass.SEMANTIC_MEMORY
    assert items[0].freshness == "2026-07-10"
    assert "rev1" in items[0].provenance


def test_adapt_wisdom_entries_maps_to_episode() -> None:
    entries = [
        WisdomEntry(id="w1", timestamp="2026-07-11", content="learned something", tags=["x"], source_ref="ref"),
    ]
    items = adapt_wisdom_entries(entries)
    assert len(items) == 1
    assert items[0].item_id == "wisdom_entry:w1"
    assert items[0].source == SourceClass.EPISODE
    assert items[0].freshness == "2026-07-11"
    assert items[0].provenance == "ref"


def test_adapt_clarify_facts_produces_one_item_per_fact_with_conflict_key() -> None:
    facts = [
        {"id": "q1", "answer": "yes, use React", "at": "2026-07-12T00:00:00Z"},
        {"id": "q2", "fact": "deploy target is AWS", "at": "2026-07-12T00:01:00Z"},
        {"id": "", "answer": "no id, dropped"},
    ]
    items = adapt_clarify_facts(facts)
    assert len(items) == 2
    assert all(item.source == SourceClass.RUNTIME_STATE for item in items)
    ids = {item.item_id for item in items}
    assert ids == {"clarify_fact:q1", "clarify_fact:q2"}
    # conflict_key is per-fact (keyed by question id), not a shared slot —
    # two different clarify facts must never compete with each other.
    assert len({item.conflict_key for item in items}) == 2


def test_adapt_goal_ledger_uses_index_based_item_id() -> None:
    entries = [
        {"event": "plan approved", "phase": "plan", "note": "v1"},
        {"event": "", "phase": "skipped"},
        {"event": "execution started", "phase": "execute"},
    ]
    items = adapt_goal_ledger(entries)
    assert [item.item_id for item in items] == ["goal_ledger:0", "goal_ledger:2"]
    assert all(item.source == SourceClass.RUNTIME_STATE for item in items)
    assert "plan approved" in items[0].content
    assert "v1" in items[0].content


def test_adapted_items_flow_through_select_context_end_to_end() -> None:
    """Integration check: adapter output is valid ContextItem input to the
    real selector, not just structurally similar."""
    plan_item = ContextItem(
        "plan", SourceClass.APPROVED_PLAN, "ship it", authority=100, relevance=100, estimated_tokens=4,
    )
    project_md_item = adapt_project_md("# Project\n\ncontext")
    facts_items = adapt_clarify_facts([{"id": "q1", "answer": "use React", "at": "2026-07-12"}])
    assert project_md_item is not None

    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset({SourceClass.PROJECT_DOC, SourceClass.RUNTIME_STATE}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )

    manifest = select_context(need, (plan_item, project_md_item, *facts_items))

    included_ids = {item.item_id for item in manifest.included}
    assert included_ids == {"plan", "project_md", "clarify_fact:q1"}
