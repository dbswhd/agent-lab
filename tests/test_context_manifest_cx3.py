"""CX3 (09-context-engineering.md §11) — ContextItem/ContextManifest
provenance/freshness/security.

Covers CX3's three acceptance criteria directly:
- every included item has a source ref/reason (provenance) — or is flagged by
  manifest_provenance_gaps() if not
- an excluded required item surfaces as an error (already true of
  select_context(); pinned here under the CX3 label)
- a built manifest never carries secret/credential content raw

2026-07-16 review: PII was removed from the redacted set — CX3's own
acceptance criteria only names "secret", and destructively redacting PII to
a placeholder breaks task utility that needs the real value (e.g. "email
the user"). Real PII handling belongs to a CX6 adapter (stable
pseudonymization via a token registry, not covered here). See
REDACTED_SECURITY_LABELS's docstring in recipe.py.
"""

from __future__ import annotations

import pytest

from agent_lab.context.recipe import (
    REDACTED_CONTENT_PLACEHOLDER,
    ActivityKind,
    ContextItem,
    ContextNeed,
    ContextSelectionError,
    SourceClass,
    manifest_provenance_gaps,
    select_context,
)

NEED = ContextNeed(
    activity=ActivityKind.EXECUTE,
    required_sources=frozenset({SourceClass.APPROVED_PLAN}),
    optional_sources=frozenset({SourceClass.EVIDENCE}),
    forbidden_sources=frozenset(),
    token_budget=1_000,
)


def test_secret_labeled_item_is_redacted_in_the_manifest() -> None:
    items = (
        ContextItem(
            "plan",
            SourceClass.APPROVED_PLAN,
            "ship it",
            authority=100,
            relevance=100,
            estimated_tokens=4,
            provenance="plan.md#rev3",
            security_label="project",
        ),
        ContextItem(
            "api-key",
            SourceClass.EVIDENCE,
            "sk-live-abc123",
            authority=50,
            relevance=50,
            estimated_tokens=4,
            provenance="evidence.jsonl#7",
            security_label="secret",
        ),
    )

    manifest = select_context(NEED, items)

    redacted_item = next(item for item in manifest.included if item.item_id == "api-key")
    assert redacted_item.content == REDACTED_CONTENT_PLACEHOLDER
    assert "sk-live-abc123" not in [item.content for item in manifest.included]
    assert manifest.redacted == ("api-key",)
    # provenance survives redaction — still traceable, just not raw.
    assert redacted_item.provenance == "evidence.jsonl#7"


@pytest.mark.parametrize("label", ["secret", "credential"])
def test_no_raw_content_for_any_redacted_label_reaches_the_manifest(label: str) -> None:
    items = (
        ContextItem(
            "plan",
            SourceClass.APPROVED_PLAN,
            "ship it",
            authority=100,
            relevance=100,
            estimated_tokens=4,
            provenance="plan.md",
        ),
        ContextItem(
            "sensitive",
            SourceClass.EVIDENCE,
            "raw sensitive payload",
            authority=50,
            relevance=50,
            estimated_tokens=4,
            provenance="evidence.jsonl",
            security_label=label,
        ),
    )

    manifest = select_context(NEED, items)

    assert all("raw sensitive payload" != item.content for item in manifest.included)


def test_pii_passes_through_unredacted_pending_cx6_pseudonymization() -> None:
    """2026-07-16 review — deliberate: destructive redaction would break task
    utility (e.g. 'email the user'). Real PII handling is CX6's job (stable
    PERSON_1/EMAIL_1-style tokens via a token registry), not CX3's."""
    items = (
        ContextItem(
            "plan",
            SourceClass.APPROVED_PLAN,
            "ship it",
            authority=100,
            relevance=100,
            estimated_tokens=4,
            provenance="plan.md",
        ),
        ContextItem(
            "contact",
            SourceClass.EVIDENCE,
            "jane@example.com",
            authority=50,
            relevance=50,
            estimated_tokens=4,
            provenance="evidence.jsonl",
            security_label="pii",
        ),
    )

    manifest = select_context(NEED, items)

    assert "jane@example.com" in [item.content for item in manifest.included]
    assert manifest.redacted == ()


def test_public_and_project_labels_are_not_redacted() -> None:
    items = (
        ContextItem(
            "plan",
            SourceClass.APPROVED_PLAN,
            "ship it",
            authority=100,
            relevance=100,
            estimated_tokens=4,
            provenance="plan.md",
            security_label="public",
        ),
    )

    manifest = select_context(NEED, items)

    assert manifest.included[0].content == "ship it"
    assert manifest.redacted == ()


def test_missing_required_source_surfaces_as_an_error() -> None:
    with pytest.raises(ContextSelectionError, match="missing required sources"):
        select_context(NEED, ())


def test_manifest_provenance_gaps_flags_items_with_no_provenance() -> None:
    items = (
        ContextItem(
            "plan",
            SourceClass.APPROVED_PLAN,
            "ship it",
            authority=100,
            relevance=100,
            estimated_tokens=4,
            provenance="",
        ),
    )

    manifest = select_context(NEED, items)

    assert manifest_provenance_gaps(manifest) == ("plan",)


def test_manifest_provenance_gaps_is_empty_when_every_item_has_provenance() -> None:
    items = (
        ContextItem(
            "plan",
            SourceClass.APPROVED_PLAN,
            "ship it",
            authority=100,
            relevance=100,
            estimated_tokens=4,
            provenance="plan.md#rev3",
        ),
    )

    manifest = select_context(NEED, items)

    assert manifest_provenance_gaps(manifest) == ()
