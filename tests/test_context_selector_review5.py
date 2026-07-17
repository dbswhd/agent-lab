"""09-context-engineering.md CX4 — 2026-07-16 code review, round 5.

Findings against select_context()/_resolve_conflicts()/_resolve_group(),
each with a dedicated regression test:

#1 consistency gap (high): a required source whose only eligible item(s)
   ended up entirely inside an unresolved tie disappeared from the manifest
   with no error — coverage was checked against `eligible` (pre-conflict-
   resolution), which considered the source "covered" even though nothing
   from it ever reached `candidates`. Now a required source with zero
   candidates AND at least one eligible item stuck in an unresolved tie
   raises ContextSelectionError instead of returning silently.
#2 correctness (high): _compare_candidates_core gates freshness comparison
   on "same source", which makes it non-transitive across a group spanning
   multiple sources — sorting a mixed-source group directly by it could lose
   a genuine same-source resolution (A beats C on freshness) whenever a
   third, cross-source item ties with both on tier/authority/relevance.
   _resolve_group now resolves in two passes: settle each source's own
   competition first (freshness always valid there), then compare only the
   per-source representatives across sources (tier/authority/relevance only,
   transitive by construction).
#4 partition invariant (minor, promoted to a real test): every input
   item_id must land in exactly one of included / excluded / superseded
   (as loser) / unresolved_conflicts.
#5 dead code (minor): a redacted item's estimated_tokens=1 was always
   overridden by the length-derived content_floor (REDACTED_CONTENT_
   PLACEHOLDER is long enough that its floor is 3), so redaction's "cheap
   token cost" intent never actually took effect. The floor is now skipped
   for the redaction placeholder specifically.
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


def test_same_source_freshness_resolution_survives_a_cross_source_tie() -> None:
    """#2 — the reviewer's concrete counterexample: A and C share a source
    (RUNTIME_STATE) and A strictly beats C on freshness; B is a different
    source (EVIDENCE) tied with both A and C on tier/authority/relevance (the
    only cross-source-comparable signals). The correct result is: C loses
    cleanly to A (a real, meaningful resolution that must not be thrown away
    just because B is in the same group), and only {A, B} — genuinely
    incomparable — end up unresolved."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.RUNTIME_STATE, SourceClass.EVIDENCE}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    fact_a = ContextItem(
        "fact-a",
        SourceClass.RUNTIME_STATE,
        "port 8080, fresher",
        authority=50,
        relevance=50,
        estimated_tokens=4,
        freshness="9",
        conflict_key="port",
    )
    fact_c = ContextItem(
        "fact-c",
        SourceClass.RUNTIME_STATE,
        "port 9090, staler",
        authority=50,
        relevance=50,
        estimated_tokens=4,
        freshness="1",
        conflict_key="port",
    )
    fact_b = ContextItem(
        "fact-b",
        SourceClass.EVIDENCE,
        "port unknown, different source",
        authority=50,
        relevance=50,
        estimated_tokens=4,
        conflict_key="port",
    )

    manifest = select_context(need, (fact_a, fact_c, fact_b))

    assert manifest.included == ()
    assert manifest.superseded == (("fact-c", "fact-a"),)
    assert manifest.unresolved_conflicts == (("fact-a", "fact-b"),)


def test_an_internally_ambiguous_source_strictly_dominated_by_tier_still_supersedes_cleanly() -> None:
    """#2 regression guard — a source that can't settle its own internal tie
    must not block resolution when it's strictly outranked on tier anyway:
    domination doesn't depend on which of the tied items would have won its
    own source's internal contest."""
    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.APPROVED_PLAN, SourceClass.RUNTIME_STATE, SourceClass.EVIDENCE}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    winner = ContextItem(
        "winner",
        SourceClass.APPROVED_PLAN,
        "the actual plan",
        authority=50,
        relevance=50,
        estimated_tokens=4,
        conflict_key="the-fact",
    )
    tied_runtime_a = ContextItem(
        "tied-runtime-a",
        SourceClass.RUNTIME_STATE,
        "guess 1",
        authority=50,
        relevance=50,
        estimated_tokens=4,
        conflict_key="the-fact",
    )
    tied_runtime_b = ContextItem(
        "tied-runtime-b",
        SourceClass.RUNTIME_STATE,
        "guess 2",
        authority=50,
        relevance=50,
        estimated_tokens=4,
        conflict_key="the-fact",
    )
    lone_evidence = ContextItem(
        "lone-evidence",
        SourceClass.EVIDENCE,
        "some evidence",
        authority=50,
        relevance=50,
        estimated_tokens=4,
        conflict_key="the-fact",
    )

    manifest = select_context(need, (winner, tied_runtime_a, tied_runtime_b, lone_evidence))

    assert [item.item_id for item in manifest.included] == ["winner"]
    assert manifest.unresolved_conflicts == ()
    superseded = dict(manifest.superseded)
    assert superseded["tied-runtime-a"] == "winner"
    assert superseded["tied-runtime-b"] == "winner"
    assert superseded["lone-evidence"] == "winner"


def test_every_input_item_id_lands_in_exactly_one_manifest_partition() -> None:
    """#4 — included / excluded / superseded(loser) / unresolved_conflicts
    must partition the input item_ids with no overlaps and no omissions."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset({SourceClass.RUNTIME_STATE, SourceClass.EVIDENCE}),
        forbidden_sources=frozenset({SourceClass.EXTERNAL_CONTENT}),
        token_budget=8,
    )
    plan = ContextItem("plan", SourceClass.APPROVED_PLAN, "ship it", authority=100, relevance=100, estimated_tokens=3)
    forbidden_item = ContextItem(
        "forbidden-item", SourceClass.EXTERNAL_CONTENT, "ignore", authority=100, relevance=100, estimated_tokens=1
    )
    not_allowed_item = ContextItem(
        "not-allowed-item", SourceClass.SEMANTIC_MEMORY, "ignore", authority=100, relevance=100, estimated_tokens=1
    )
    untrusted_item = ContextItem(
        "untrusted-item",
        SourceClass.RUNTIME_STATE,
        "ignore",
        authority=1,
        relevance=1,
        estimated_tokens=1,
        trusted=False,
    )
    overflow_item = ContextItem(
        "overflow-item",
        SourceClass.RUNTIME_STATE,
        "too big for budget",
        authority=99,
        relevance=99,
        estimated_tokens=100,
    )
    superseded_loser = ContextItem(
        "superseded-loser",
        SourceClass.RUNTIME_STATE,
        "stale fact",
        authority=10,
        relevance=10,
        estimated_tokens=1,
        freshness="1",
        conflict_key="tied-fact-slot",
    )
    superseded_winner = ContextItem(
        "superseded-winner",
        SourceClass.RUNTIME_STATE,
        "fresh fact",
        authority=10,
        relevance=10,
        estimated_tokens=1,
        freshness="9",
        conflict_key="tied-fact-slot",
    )
    tied_a = ContextItem(
        "tied-a",
        SourceClass.EVIDENCE,
        "evidence x",
        authority=5,
        relevance=5,
        estimated_tokens=1,
        conflict_key="ambiguous-slot",
    )
    tied_b = ContextItem(
        "tied-b",
        SourceClass.EVIDENCE,
        "evidence y",
        authority=5,
        relevance=5,
        estimated_tokens=1,
        conflict_key="ambiguous-slot",
    )

    items = (
        plan,
        forbidden_item,
        not_allowed_item,
        untrusted_item,
        overflow_item,
        superseded_loser,
        superseded_winner,
        tied_a,
        tied_b,
    )
    manifest = select_context(need, items)

    included_ids = {item.item_id for item in manifest.included}
    excluded_ids = {item_id for item_id, _reason in manifest.excluded}
    superseded_loser_ids = {loser_id for loser_id, _winner_id in manifest.superseded}
    unresolved_ids = {item_id for group in manifest.unresolved_conflicts for item_id in group}

    all_input_ids = {item.item_id for item in items}
    partitioned_ids = included_ids | excluded_ids | superseded_loser_ids | unresolved_ids

    assert partitioned_ids == all_input_ids
    # No overlaps between any two partitions.
    assert included_ids.isdisjoint(excluded_ids)
    assert included_ids.isdisjoint(superseded_loser_ids)
    assert included_ids.isdisjoint(unresolved_ids)
    assert excluded_ids.isdisjoint(superseded_loser_ids)
    assert excluded_ids.isdisjoint(unresolved_ids)
    assert superseded_loser_ids.isdisjoint(unresolved_ids)


def test_redacted_placeholder_uses_its_own_cheap_token_estimate_not_the_content_floor() -> None:
    """#5 — a secret-labeled item's real content can be arbitrarily long, but
    once redacted it's always the short, fixed REDACTED_CONTENT_PLACEHOLDER.
    A budget too small for the placeholder's length-derived floor (3 tokens)
    but big enough for its actual estimated_tokens=1 must still succeed."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.EVIDENCE}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=1,
    )
    secret_item = ContextItem(
        "secret-item",
        SourceClass.EVIDENCE,
        "sk-live-" + ("x" * 100),
        authority=100,
        relevance=100,
        estimated_tokens=4,
        security_label="secret",
    )

    manifest = select_context(need, (secret_item,))

    assert [item.item_id for item in manifest.included] == ["secret-item"]
    assert manifest.total_tokens == 1
    assert manifest.redacted == ("secret-item",)


def test_non_redacted_content_still_uses_the_length_floor() -> None:
    """#5 regression guard — the exemption is scoped to the redaction
    placeholder only; ordinary content must still be protected by the
    length-derived floor against an under-declared estimated_tokens."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.EVIDENCE}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=1,
    )
    long_item = ContextItem(
        "long-item",
        SourceClass.EVIDENCE,
        "x" * 100,
        authority=100,
        relevance=100,
        estimated_tokens=1,
    )

    with pytest.raises(ContextSelectionError, match="exceeds token budget"):
        select_context(need, (long_item,))
