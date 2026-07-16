"""CX4 (09-context-engineering.md §11) — deterministic selector.

Covers CX4's three acceptance criteria:
- same input always produces the same selection (determinism)
- conflict rule excludes an old plan revision in favor of the latest
  approved one (09 doc §5 example: "old plan vs approved latest plan: old
  plan 제외")
- budget overflow follows the defined trim order (§7.2) — steps 1
  (exact-duplicate removal) and 2 (drop low authority/relevance first) are
  implemented in select_context() itself; steps 3-6 need real content
  compression (tool-output-to-artifact-ref, transcript summarization,
  symbol-targeted repo snippets) which select_context() can't do — it
  operates on already-built ContextItems, not raw sources. That gap is
  logged, not silently claimed as done.
"""

from __future__ import annotations

from agent_lab.context.recipe import (
    ActivityKind,
    ContextItem,
    ContextNeed,
    SourceClass,
    select_context,
)

NEED = ContextNeed(
    activity=ActivityKind.PLAN,
    required_sources=frozenset({SourceClass.APPROVED_PLAN}),
    optional_sources=frozenset({SourceClass.REPO_CONTEXT, SourceClass.SEMANTIC_MEMORY}),
    forbidden_sources=frozenset(),
    token_budget=1_000,
)


def test_same_input_produces_the_same_manifest_every_time() -> None:
    items = (
        ContextItem("plan", SourceClass.APPROVED_PLAN, "ship it", authority=100, relevance=100, estimated_tokens=4),
        ContextItem("repo-a", SourceClass.REPO_CONTEXT, "a", authority=50, relevance=50, estimated_tokens=4),
        ContextItem("repo-b", SourceClass.REPO_CONTEXT, "b", authority=50, relevance=40, estimated_tokens=4),
    )

    manifests = [select_context(NEED, items) for _ in range(20)]

    first = manifests[0]
    for manifest in manifests[1:]:
        assert manifest.included == first.included
        assert manifest.excluded == first.excluded
        assert manifest.superseded == first.superseded
        assert manifest.total_tokens == first.total_tokens


def test_old_plan_revision_is_superseded_by_the_latest_approved_one() -> None:
    """09 doc §5 example: 'old plan vs approved latest plan: old plan 제외'."""
    old_plan = ContextItem(
        "plan-rev2", SourceClass.APPROVED_PLAN, "old scope",
        authority=100, relevance=100, estimated_tokens=4,
        freshness="0002", conflict_key="current-plan",
    )
    latest_plan = ContextItem(
        "plan-rev3", SourceClass.APPROVED_PLAN, "new scope",
        authority=100, relevance=100, estimated_tokens=4,
        freshness="0003", conflict_key="current-plan",
    )

    manifest = select_context(NEED, (old_plan, latest_plan))

    assert [item.item_id for item in manifest.included] == ["plan-rev3"]
    assert manifest.superseded == (("plan-rev2", "plan-rev3"),)


def test_conflict_resolution_prefers_higher_priority_tier_over_lower() -> None:
    """§5 tier order: approved plan (tier 2) beats semantic memory (tier 5) for
    the same fact, regardless of which has higher authority/freshness."""
    stale_memory = ContextItem(
        "memory-guess", SourceClass.SEMANTIC_MEMORY, "guessed scope",
        authority=100, relevance=100, estimated_tokens=4,
        freshness="9999", conflict_key="current-plan",
    )
    approved_plan = ContextItem(
        "plan-rev1", SourceClass.APPROVED_PLAN, "actual scope",
        authority=10, relevance=10, estimated_tokens=4,
        freshness="0001", conflict_key="current-plan",
    )

    manifest = select_context(NEED, (stale_memory, approved_plan))

    assert [item.item_id for item in manifest.included] == ["plan-rev1"]
    assert manifest.superseded == (("memory-guess", "plan-rev1"),)


def test_stale_repo_snippet_cannot_outrank_current_runtime_state_on_a_tie() -> None:
    """2026-07-16 review — REPO_CONTEXT moved from tier 3 to tier 4 (was sharing
    a tier with RUNTIME_STATE/EVIDENCE, so a high-authority/fresh-looking but
    commit-stale repo snippet could win a conflict against genuinely current
    runtime fact; repo content lags live state and shouldn't contend at the
    same tier)."""
    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset({SourceClass.REPO_CONTEXT, SourceClass.RUNTIME_STATE}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    stale_repo = ContextItem(
        "repo-old-sha", SourceClass.REPO_CONTEXT, "old file contents",
        authority=100, relevance=100, estimated_tokens=4,
        freshness="9999", conflict_key="current-file-state",
    )
    current_runtime = ContextItem(
        "runtime-now", SourceClass.RUNTIME_STATE, "current file state",
        authority=10, relevance=10, estimated_tokens=4,
        freshness="0001", conflict_key="current-file-state",
    )
    plan = ContextItem(
        "plan", SourceClass.APPROVED_PLAN, "ship it", authority=100, relevance=100, estimated_tokens=4,
    )

    manifest = select_context(need, (stale_repo, current_runtime, plan))

    included_ids = {item.item_id for item in manifest.included}
    assert included_ids == {"plan", "runtime-now"}
    assert manifest.superseded == (("repo-old-sha", "runtime-now"),)


def test_exact_duplicate_content_is_deduplicated_before_budget_selection() -> None:
    """§7.2 trim step 1: exact duplicate 제거."""
    items = (
        ContextItem("plan", SourceClass.APPROVED_PLAN, "ship it", authority=100, relevance=100, estimated_tokens=4),
        ContextItem("plan-dup", SourceClass.APPROVED_PLAN, "ship it", authority=90, relevance=90, estimated_tokens=4),
    )

    manifest = select_context(NEED, items)

    assert len(manifest.included) == 1
    assert manifest.included[0].item_id == "plan"  # higher authority wins the tie
    assert manifest.superseded == (("plan-dup", "plan"),)


def test_low_authority_item_is_trimmed_before_high_authority_when_over_budget() -> None:
    """§7.2 trim step 2: 낮은 authority/관련성 item 제거 — already implemented via
    the existing authority/relevance ranking; pinned here under the CX4 label."""
    tight_need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset({SourceClass.REPO_CONTEXT}),
        forbidden_sources=frozenset(),
        token_budget=4,
    )
    items = (
        ContextItem("plan", SourceClass.APPROVED_PLAN, "ship", authority=100, relevance=100, estimated_tokens=2),
        ContextItem("repo-high", SourceClass.REPO_CONTEXT, "hi", authority=90, relevance=90, estimated_tokens=2),
        ContextItem("repo-low", SourceClass.REPO_CONTEXT, "lo", authority=10, relevance=10, estimated_tokens=2),
    )

    manifest = select_context(tight_need, items)

    included_ids = {item.item_id for item in manifest.included}
    assert "plan" in included_ids
    assert "repo-high" in included_ids
    assert "repo-low" not in included_ids
