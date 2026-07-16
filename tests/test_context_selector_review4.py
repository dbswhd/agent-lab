"""09-context-engineering.md CX4 — 2026-07-16 code review, round 4.

Four findings against select_context()/_resolve_conflicts()/_resolve_group(),
each with a dedicated regression test:

#1 real bug (§5): a genuinely unresolvable conflict — items tied on every
   meaningful signal (tier, authority, same-source freshness, relevance) —
   used to fall through to an item_id string comparison and silently pick a
   "winner". §5 requires this to escalate to structured ambiguity / Human
   decision instead of deciding a real contradiction arbitrarily.
#2 real bug: content-only dedup ran before conflict_key resolution, so two
   items that declared DIFFERENT explicit conflict_keys but happened to share
   identical text were wrongly merged — losing one conflict_key slot's only
   representative before it ever got a chance to be evaluated on its own.
#3 observability gap: ContextManifest.excluded/superseded were flat item_id
   tuples with no reason or "who won" — now (item_id, reason) and
   (loser_id, winner_id) pairs respectively.
#4 contract gap: no validation that item_id is unique among the items passed
   into select_context() — a duplicate could corrupt the redacted/excluded/
   superseded bookkeeping, which all key off item_id.
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


def test_fully_tied_conflict_key_group_escalates_instead_of_picking_a_winner() -> None:
    """#1 — two RUNTIME_STATE facts, same conflict_key, same authority/
    relevance, no freshness set on either: nothing distinguishes them except
    item_id. Neither should be included or marked superseded; both surface in
    unresolved_conflicts for a caller to actually escalate."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.RUNTIME_STATE}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    fact_a = ContextItem(
        "fact-a", SourceClass.RUNTIME_STATE, "the port is 8080",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="listening-port",
    )
    fact_b = ContextItem(
        "fact-b", SourceClass.RUNTIME_STATE, "the port is 9090",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="listening-port",
    )

    manifest = select_context(need, (fact_a, fact_b))

    assert manifest.included == ()
    assert manifest.superseded == ()
    assert manifest.unresolved_conflicts == (("fact-a", "fact-b"),)


def test_cross_source_tie_with_no_freshness_signal_also_escalates() -> None:
    """#1 — same tier (RUNTIME_STATE and EVIDENCE both tier 3), same
    authority/relevance, different sources so the same-source-only freshness
    tiebreak never engages. Still a genuine tie, still escalates."""
    need = ContextNeed(
        activity=ActivityKind.REPAIR,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.RUNTIME_STATE, SourceClass.EVIDENCE}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    runtime_fact = ContextItem(
        "runtime-fact", SourceClass.RUNTIME_STATE, "build is green",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="build-status",
    )
    evidence_fact = ContextItem(
        "evidence-fact", SourceClass.EVIDENCE, "build is red",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="build-status",
    )

    manifest = select_context(need, (runtime_fact, evidence_fact))

    assert manifest.included == ()
    assert manifest.unresolved_conflicts == (("evidence-fact", "runtime-fact"),)


def test_a_real_signal_difference_still_resolves_cleanly_not_a_false_tie() -> None:
    """#1 regression guard — the escalation path must not over-fire: any
    genuine distinguishing signal (here, relevance) still produces a clear
    winner, same as before this change."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.RUNTIME_STATE}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    more_relevant = ContextItem(
        "more-relevant", SourceClass.RUNTIME_STATE, "the port is 8080",
        authority=50, relevance=60, estimated_tokens=4, conflict_key="listening-port",
    )
    less_relevant = ContextItem(
        "less-relevant", SourceClass.RUNTIME_STATE, "the port is 9090",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="listening-port",
    )

    manifest = select_context(need, (more_relevant, less_relevant))

    assert [item.item_id for item in manifest.included] == ["more-relevant"]
    assert manifest.superseded == (("less-relevant", "more-relevant"),)
    assert manifest.unresolved_conflicts == ()


def test_required_source_fully_consumed_by_an_unresolved_tie_raises_not_silently_missing() -> None:
    """#1 (2026-07-16 review round 5) — a required source whose ONLY
    candidates are genuinely tied must not return a manifest that simply
    omits the source. It's not "missing" in the pre-conflict-resolution
    sense (raising via the generic "missing required sources" message would
    be misleading, since the source WAS eligible) — but silently succeeding
    would violate CX3's "excluded required item은 오류로 드러난다" and §12's
    "required가 목적에 맞게 들어간다": unresolved_conflicts is advisory, and a
    caller that doesn't inspect it would proceed with no representation of
    this required fact at all. A dedicated error names the ambiguity."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.RUNTIME_STATE}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    fact_a = ContextItem(
        "fact-a", SourceClass.RUNTIME_STATE, "the port is 8080",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="listening-port",
    )
    fact_b = ContextItem(
        "fact-b", SourceClass.RUNTIME_STATE, "the port is 9090",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="listening-port",
    )

    with pytest.raises(ContextSelectionError, match="required source unresolved: runtime_state"):
        select_context(need, (fact_a, fact_b))


def test_required_source_partially_consumed_by_an_unresolved_tie_still_succeeds_via_its_other_item() -> None:
    """#1 regression guard — if the required source has ANOTHER eligible item
    that DOES survive into candidates, the source is genuinely represented
    and must not hard-fail just because a different fact/slot from the same
    source happened to hit an unresolved tie elsewhere."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.RUNTIME_STATE}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    tied_a = ContextItem(
        "tied-a", SourceClass.RUNTIME_STATE, "the port is 8080",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="listening-port",
    )
    tied_b = ContextItem(
        "tied-b", SourceClass.RUNTIME_STATE, "the port is 9090",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="listening-port",
    )
    clean_fact = ContextItem(
        "clean-fact", SourceClass.RUNTIME_STATE, "build is green",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="build-status",
    )

    manifest = select_context(need, (tied_a, tied_b, clean_fact))

    assert [item.item_id for item in manifest.included] == ["clean-fact"]
    assert manifest.unresolved_conflicts == (("tied-a", "tied-b"),)


def test_required_source_cleanly_superseded_by_a_different_source_still_succeeds() -> None:
    """#1 regression guard — the original round-2 #2 policy must still hold:
    a required source's sole item losing a CLEAN (not tied) conflict_key
    contest to a different, higher-tier source's representative of the same
    fact is intentional, not a coverage gap, and must not raise."""
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
    assert manifest.unresolved_conflicts == ()


def test_different_conflict_keys_are_never_merged_by_incidental_content_equality() -> None:
    """#2 — A declares conflict_key="plan-slot", B declares
    conflict_key="config-slot"; both happen to hold the text "pending".
    Declaring different conflict_keys is an explicit "we are different facts"
    assertion that must outrank incidental content equality — both must
    survive independently, not collapse into one via content-dedup."""
    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.RUNTIME_STATE}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    plan_slot = ContextItem(
        "plan-slot-item", SourceClass.RUNTIME_STATE, "pending",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="plan-slot",
    )
    config_slot = ContextItem(
        "config-slot-item", SourceClass.RUNTIME_STATE, "pending",
        authority=50, relevance=50, estimated_tokens=4, conflict_key="config-slot",
    )

    manifest = select_context(need, (plan_slot, config_slot))

    included_ids = {item.item_id for item in manifest.included}
    assert included_ids == {"plan-slot-item", "config-slot-item"}
    assert manifest.superseded == ()
    assert manifest.unresolved_conflicts == ()


def test_same_conflict_key_and_same_content_still_deduplicates_to_one_winner() -> None:
    """#2 regression guard — items that DO share a conflict_key (or both lack
    one) must still collapse via the normal higher-authority-wins rule; the
    fix only stops DIFFERENT conflict_keys from being merged by content."""
    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.RUNTIME_STATE}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    stronger = ContextItem(
        "stronger", SourceClass.RUNTIME_STATE, "pending",
        authority=90, relevance=50, estimated_tokens=4, conflict_key="plan-slot",
    )
    weaker = ContextItem(
        "weaker", SourceClass.RUNTIME_STATE, "pending",
        authority=10, relevance=50, estimated_tokens=4, conflict_key="plan-slot",
    )

    manifest = select_context(need, (stronger, weaker))

    assert [item.item_id for item in manifest.included] == ["stronger"]
    assert manifest.superseded == (("weaker", "stronger"),)


def test_untagged_items_with_no_conflict_key_still_dedup_by_content() -> None:
    """#2 regression guard — the original round-2 #4 fix (cross-source exact-
    duplicate dedup for items with no conflict_key at all) must still work:
    both items normalize to conflict_key="" for the dedup key, so identical
    content still collapses to one, budget-authority-tiebreak as before."""
    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.PROJECT_DOC, SourceClass.REPO_CONTEXT}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    doc_copy = ContextItem(
        "doc-copy", SourceClass.PROJECT_DOC, "the same snippet verbatim",
        authority=90, relevance=50, estimated_tokens=4,
    )
    repo_copy = ContextItem(
        "repo-copy", SourceClass.REPO_CONTEXT, "the same snippet verbatim",
        authority=10, relevance=50, estimated_tokens=4,
    )

    manifest = select_context(need, (doc_copy, repo_copy))

    assert [item.item_id for item in manifest.included] == ["doc-copy"]
    assert manifest.superseded == (("repo-copy", "doc-copy"),)


def test_excluded_items_carry_their_specific_reason() -> None:
    """#3 — forbidden / not_allowed / untrusted / budget_overflow must each be
    individually visible instead of collapsed into one undifferentiated
    tuple of item_ids."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset({SourceClass.REPO_CONTEXT}),
        forbidden_sources=frozenset({SourceClass.EXTERNAL_CONTENT}),
        token_budget=5,
    )
    plan = ContextItem("plan", SourceClass.APPROVED_PLAN, "ship it", authority=100, relevance=100, estimated_tokens=3)
    forbidden_item = ContextItem("forbidden-item", SourceClass.EXTERNAL_CONTENT, "ignore", authority=100, relevance=100, estimated_tokens=1)
    not_allowed_item = ContextItem("not-allowed-item", SourceClass.SEMANTIC_MEMORY, "ignore", authority=100, relevance=100, estimated_tokens=1)
    untrusted_item = ContextItem(
        "untrusted-item", SourceClass.REPO_CONTEXT, "ignore",
        authority=1, relevance=1, estimated_tokens=1, trusted=False,
    )
    overflow_item = ContextItem("overflow-item", SourceClass.REPO_CONTEXT, "too big to fit", authority=99, relevance=99, estimated_tokens=100)

    manifest = select_context(need, (plan, forbidden_item, not_allowed_item, untrusted_item, overflow_item))

    excluded = dict(manifest.excluded)
    assert excluded["forbidden-item"] == "forbidden"
    assert excluded["not-allowed-item"] == "not_allowed"
    assert excluded["untrusted-item"] == "untrusted"
    assert excluded["overflow-item"] == "budget_overflow"


def test_superseded_pairs_record_the_winning_item_id() -> None:
    """#3 — a superseded entry names who beat it, not just who lost."""
    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    old_plan = ContextItem(
        "plan-old", SourceClass.APPROVED_PLAN, "old scope",
        authority=100, relevance=100, estimated_tokens=4, freshness="0001", conflict_key="current-plan",
    )
    new_plan = ContextItem(
        "plan-new", SourceClass.APPROVED_PLAN, "new scope",
        authority=100, relevance=100, estimated_tokens=4, freshness="0002", conflict_key="current-plan",
    )

    manifest = select_context(need, (old_plan, new_plan))

    assert manifest.superseded == (("plan-old", "plan-new"),)


def test_duplicate_item_id_is_rejected() -> None:
    """#4 — two distinct ContextItems must never share an item_id; downstream
    bookkeeping (redacted/excluded/superseded, all keyed by item_id) can't
    tell them apart otherwise."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.REPO_CONTEXT}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    first = ContextItem("dup", SourceClass.REPO_CONTEXT, "first version", authority=50, relevance=50, estimated_tokens=4)
    second = ContextItem("dup", SourceClass.REPO_CONTEXT, "second version", authority=10, relevance=10, estimated_tokens=4)

    with pytest.raises(ContextSelectionError, match="duplicate item_id"):
        select_context(need, (first, second))


def test_unique_item_ids_are_unaffected_by_the_new_check() -> None:
    """#4 sanity check — the guard must not false-positive on ordinary input."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.REPO_CONTEXT}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    items = (
        ContextItem("a", SourceClass.REPO_CONTEXT, "content a", authority=50, relevance=50, estimated_tokens=4),
        ContextItem("b", SourceClass.REPO_CONTEXT, "content b", authority=50, relevance=50, estimated_tokens=4),
    )

    manifest = select_context(need, items)

    assert {item.item_id for item in manifest.included} == {"a", "b"}
