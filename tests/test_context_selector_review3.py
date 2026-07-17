"""09-context-engineering.md CX3/CX4 — 2026-07-16 code review, round 2.

Five findings against ContextItem/ContextNeed construction and
_resolve_conflicts()'s grouping, each with a dedicated regression test:

#1 security: security_label had no validation — a typo'd or non-standard
   label silently bypassed redaction (fail-open).
#2 data bug: conflict_key="" grouped with every other "" item as if they
   contested the same fact/slot.
#3 data bug: content="" grouped with every other "" item as an exact
   duplicate.
#4 guardrail: ContextNeed didn't reject required_sources/forbidden_sources
   (or optional_sources/forbidden_sources) overlap at construction — an
   impossible recipe failed later with a misleading "missing required
   sources" error instead of a clear one at the point of the mistake.
#5 reference improvement: EXTERNAL_CONTENT now defaults to trusted=False
   (09 doc §8's untrusted-content boundary) unless the caller explicitly
   overrides it; AGENT_OPINION is deliberately left trusted=True by default
   since it's a weighting concern (tier 6, low authority), not an
   injection-safety one.
"""

from __future__ import annotations

import pytest

from agent_lab.context.recipe import (
    ActivityKind,
    ContextItem,
    ContextNeed,
    SourceClass,
    select_context,
)


@pytest.mark.parametrize("label", ["secrt", "internal", "SECRET", " secret", ""])
def test_unknown_security_label_is_rejected_at_construction(label: str) -> None:
    """#1 — fail closed: a typo'd or non-standard label must not silently
    bypass redaction by falling outside REDACTED_SECURITY_LABELS."""
    with pytest.raises(ValueError, match="unknown security_label"):
        ContextItem(
            "x", SourceClass.EVIDENCE, "sensitive", authority=50, relevance=50, estimated_tokens=1, security_label=label
        )


@pytest.mark.parametrize("label", ["public", "project", "secret", "credential", "pii"])
def test_every_declared_security_label_is_accepted(label: str) -> None:
    item = ContextItem(
        "x", SourceClass.EVIDENCE, "content", authority=50, relevance=50, estimated_tokens=1, security_label=label
    )
    assert item.security_label == label


def test_empty_conflict_key_does_not_group_unrelated_items() -> None:
    """#2 — conflict_key="" must behave like conflict_key=None (no grouping),
    not like a real shared slot that supersedes one of the items."""
    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset({SourceClass.REPO_CONTEXT}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    plan = ContextItem("plan", SourceClass.APPROVED_PLAN, "ship it", authority=100, relevance=100, estimated_tokens=4)
    repo_a = ContextItem(
        "repo-a", SourceClass.REPO_CONTEXT, "file a", authority=50, relevance=50, estimated_tokens=4, conflict_key=""
    )
    repo_b = ContextItem(
        "repo-b", SourceClass.REPO_CONTEXT, "file b", authority=50, relevance=50, estimated_tokens=4, conflict_key=""
    )

    manifest = select_context(need, (plan, repo_a, repo_b))

    included_ids = {item.item_id for item in manifest.included}
    assert included_ids == {"plan", "repo-a", "repo-b"}
    assert manifest.superseded == ()


def test_empty_content_items_are_not_treated_as_exact_duplicates() -> None:
    """#3 — two genuinely different, independently-empty items (an empty file
    summary and an empty tool result, say) must not collapse into one."""
    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset({SourceClass.REPO_CONTEXT}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    plan = ContextItem("plan", SourceClass.APPROVED_PLAN, "ship it", authority=100, relevance=100, estimated_tokens=4)
    empty_a = ContextItem("empty-a", SourceClass.REPO_CONTEXT, "", authority=50, relevance=50, estimated_tokens=1)
    empty_b = ContextItem("empty-b", SourceClass.REPO_CONTEXT, "", authority=40, relevance=40, estimated_tokens=1)

    manifest = select_context(need, (plan, empty_a, empty_b))

    included_ids = {item.item_id for item in manifest.included}
    assert included_ids == {"plan", "empty-a", "empty-b"}
    assert manifest.superseded == ()


def test_required_and_forbidden_overlap_is_rejected_at_recipe_construction() -> None:
    """#4 — an impossible recipe (a source both required and forbidden) fails
    immediately with a clear message, not later as a misleading "missing
    required sources" error from select_context()."""
    with pytest.raises(ValueError, match="required_sources and forbidden_sources overlap"):
        ContextNeed(
            activity=ActivityKind.PLAN,
            required_sources=frozenset({SourceClass.REPO_CONTEXT}),
            optional_sources=frozenset(),
            forbidden_sources=frozenset({SourceClass.REPO_CONTEXT}),
            token_budget=1_000,
        )


def test_optional_and_forbidden_overlap_is_also_rejected() -> None:
    with pytest.raises(ValueError, match="optional_sources and forbidden_sources overlap"):
        ContextNeed(
            activity=ActivityKind.PLAN,
            required_sources=frozenset({SourceClass.APPROVED_PLAN}),
            optional_sources=frozenset({SourceClass.REPO_CONTEXT}),
            forbidden_sources=frozenset({SourceClass.REPO_CONTEXT}),
            token_budget=1_000,
        )


def test_required_and_optional_overlap_is_still_allowed() -> None:
    """Deliberately not an error — harmless redundancy, unlike the forbidden
    overlaps above which make the recipe unsatisfiable."""
    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset({SourceClass.APPROVED_PLAN}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    assert need.required_sources == need.optional_sources == frozenset({SourceClass.APPROVED_PLAN})


def test_external_content_defaults_to_untrusted() -> None:
    """#5 — 09 doc §8's untrusted-content boundary, applied without every
    producer having to remember to pass trusted=False."""
    item = ContextItem(
        "web-1", SourceClass.EXTERNAL_CONTENT, "fetched html", authority=50, relevance=50, estimated_tokens=4
    )
    assert item.trusted is False


def test_agent_opinion_defaults_to_trusted() -> None:
    """#5 — deliberately NOT defaulted untrusted: a peer agent's proposal is a
    weighting concern (tier 6, low authority), not an injection-safety one."""
    item = ContextItem(
        "peer-proposal",
        SourceClass.AGENT_OPINION,
        "I think we should...",
        authority=20,
        relevance=50,
        estimated_tokens=4,
    )
    assert item.trusted is True


def test_explicit_trusted_true_overrides_the_external_content_default() -> None:
    item = ContextItem(
        "vetted-web",
        SourceClass.EXTERNAL_CONTENT,
        "reviewed and approved excerpt",
        authority=50,
        relevance=50,
        estimated_tokens=4,
        trusted=True,
    )
    assert item.trusted is True


def test_untrusted_external_content_is_excluded_from_the_manifest_by_default() -> None:
    """End-to-end: the #5 default actually takes effect inside select_context()."""
    need = ContextNeed(
        activity=ActivityKind.PLAN,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset({SourceClass.EXTERNAL_CONTENT}),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    plan = ContextItem("plan", SourceClass.APPROVED_PLAN, "ship it", authority=100, relevance=100, estimated_tokens=4)
    web = ContextItem(
        "web-1", SourceClass.EXTERNAL_CONTENT, "fetched html", authority=100, relevance=100, estimated_tokens=4
    )

    manifest = select_context(need, (plan, web))

    assert [item.item_id for item in manifest.included] == ["plan"]
    assert ("web-1", "untrusted") in manifest.excluded
