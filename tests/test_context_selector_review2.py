"""09-context-engineering.md CX4 — 2026-07-16 code review fixes.

Four findings against select_context()/_resolve_conflicts()/_pick_winner(),
each with a dedicated regression test:

#1 real bug: a required source with multiple candidate items raised
   ContextSelectionError as soon as ANY item of that source (even a low-
   priority extra, after the requirement was already satisfied by a better
   item) didn't fit the remaining budget.
#2 edge bug: a required source's sole item could lose a cross-source
   conflict_key contest and silently vanish from `candidates`, producing a
   false "missing required sources" error even though an eligible candidate
   existed before conflict resolution ran.
#3 correctness: freshness tie-break compared lexicographically across
   sources with incompatible formats (commit SHA vs ISO timestamp vs plan
   revision) — deterministic but meaningless as a "which is newer" signal.
#4 gap: exact-duplicate detection was keyed on (source, content), so
   identical text from two different sources both survived and consumed
   budget twice.
"""

from __future__ import annotations

import pytest

from agent_lab.context.recipe import (
    ActivityKind,
    ContextItem,
    ContextNeed,
    ContextSelectionError,
    SourceClass,
    select_context,
)


def test_extra_items_of_an_already_satisfied_required_source_are_excluded_not_fatal() -> None:
    """#1 — the first (highest-authority) REPO_CONTEXT item satisfies the
    requirement; later ones that don't fit are just excluded, not fatal."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.REPO_CONTEXT}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=5,
    )
    items = tuple(
        ContextItem(f"slice-{i}", SourceClass.REPO_CONTEXT, f"content-{i}", authority=100 - i, relevance=100 - i, estimated_tokens=3)
        for i in range(5)
    )

    manifest = select_context(need, items)

    assert [item.item_id for item in manifest.included] == ["slice-0"]
    assert ("slice-1", "budget_overflow") in manifest.excluded


def test_required_source_with_no_eligible_candidate_at_all_still_raises() -> None:
    """#1 sanity check — the fix must not swallow the genuine "budget too
    small for the only candidate" failure."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.REPO_CONTEXT}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=1,
    )
    items = (ContextItem("only-slice", SourceClass.REPO_CONTEXT, "way too much content here", authority=100, relevance=100, estimated_tokens=10),)

    with pytest.raises(ContextSelectionError, match="required context exceeds token budget"):
        select_context(need, items)


def test_required_source_superseded_by_cross_source_conflict_does_not_false_positive_missing() -> None:
    """#2 — a required REPO_CONTEXT item loses a conflict_key contest to a
    higher-tier APPROVED_PLAN item representing the same fact. That's an
    intentional supersession, not a coverage gap: select_context() must not
    raise "missing required sources" for it."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.REPO_CONTEXT}),
        optional_sources=frozenset({SourceClass.APPROVED_PLAN}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    repo_item = ContextItem(
        "repo-guess", SourceClass.REPO_CONTEXT, "inferred from file",
        authority=10, relevance=10, estimated_tokens=4, conflict_key="the-fact",
    )
    plan_item = ContextItem(
        "plan-authoritative", SourceClass.APPROVED_PLAN, "the actual fact",
        authority=100, relevance=100, estimated_tokens=4, conflict_key="the-fact",
    )

    manifest = select_context(need, (repo_item, plan_item))

    assert [item.item_id for item in manifest.included] == ["plan-authoritative"]
    assert manifest.superseded == (("repo-guess", "plan-authoritative"),)


def test_freshness_tie_break_is_ignored_across_different_sources() -> None:
    """#3 — RUNTIME_STATE and EVIDENCE share tier 3. A RUNTIME_STATE item with
    a lexicographically-larger-but-meaningless freshness string ("zzz", not a
    real timestamp format) must not beat a higher-authority EVIDENCE item —
    freshness only decides ties within the same source."""
    need = ContextNeed(
        activity=ActivityKind.REPAIR,
        required_sources=frozenset({SourceClass.EVIDENCE}),
        optional_sources=frozenset({SourceClass.RUNTIME_STATE}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    runtime_item = ContextItem(
        "runtime-noisy-freshness", SourceClass.RUNTIME_STATE, "runtime guess",
        authority=10, relevance=10, estimated_tokens=4, freshness="zzz-not-a-real-timestamp",
        conflict_key="the-fact",
    )
    evidence_item = ContextItem(
        "evidence-authoritative", SourceClass.EVIDENCE, "actual evidence",
        authority=100, relevance=100, estimated_tokens=4, freshness="2026-01-01T00:00:00Z",
        conflict_key="the-fact",
    )

    manifest = select_context(need, (runtime_item, evidence_item))

    assert [item.item_id for item in manifest.included] == ["evidence-authoritative"]
    assert manifest.superseded == (("runtime-noisy-freshness", "evidence-authoritative"),)


def test_identical_content_from_different_sources_is_deduplicated() -> None:
    """#4 — the same text quoted in both PROJECT_DOC and REPO_CONTEXT (both
    tier 4, same authority/relevance) should only be paid for once. There's no
    meaningful signal to break the tie (tier/authority/relevance all equal,
    and freshness only compares within a single source) — 2026-07-16 review
    #1 changed this from "pick one via item_id" to "escalate as an
    unresolved conflict", so the budget still isn't paid twice, but neither
    copy silently wins either."""
    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset({SourceClass.PROJECT_DOC, SourceClass.REPO_CONTEXT}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    plan = ContextItem("plan", SourceClass.APPROVED_PLAN, "ship it", authority=100, relevance=100, estimated_tokens=4)
    doc_copy = ContextItem(
        "doc-copy", SourceClass.PROJECT_DOC, "the same snippet verbatim",
        authority=50, relevance=50, estimated_tokens=4,
    )
    repo_copy = ContextItem(
        "repo-copy", SourceClass.REPO_CONTEXT, "the same snippet verbatim",
        authority=50, relevance=50, estimated_tokens=4,
    )

    manifest = select_context(need, (plan, doc_copy, repo_copy))

    included_ids = {item.item_id for item in manifest.included}
    assert included_ids == {"plan"}
    assert manifest.unresolved_conflicts == (("doc-copy", "repo-copy"),)
