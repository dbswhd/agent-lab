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


def test_context_selection_keeps_required_items_and_fits_optional_budget() -> None:
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset({SourceClass.REPO_CONTEXT, SourceClass.EPISODE}),
        forbidden_sources=frozenset(),
        token_budget=10,
    )
    items = (
        ContextItem("plan", SourceClass.APPROVED_PLAN, "plan", authority=100, relevance=100, estimated_tokens=4),
        ContextItem("repo", SourceClass.REPO_CONTEXT, "repo", authority=80, relevance=80, estimated_tokens=4),
        ContextItem("episode", SourceClass.EPISODE, "episode", authority=20, relevance=10, estimated_tokens=4),
    )
    manifest = select_context(need, items)
    assert [item.item_id for item in manifest.included] == ["plan", "repo"]
    assert manifest.excluded == (("episode", "budget_overflow"),)


def test_context_selection_rejects_missing_required_source() -> None:
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=10,
    )
    with pytest.raises(ContextSelectionError):
        select_context(need, ())


def test_context_selection_excludes_forbidden_sources() -> None:
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.REPO_CONTEXT}),
        forbidden_sources=frozenset({SourceClass.EXTERNAL_CONTENT}),
        token_budget=10,
    )
    items = (
        ContextItem(
            "external", SourceClass.EXTERNAL_CONTENT, "ignore", authority=100, relevance=100, estimated_tokens=1
        ),
        ContextItem("repo", SourceClass.REPO_CONTEXT, "repo", authority=80, relevance=80, estimated_tokens=1),
    )
    manifest = select_context(need, items)
    assert [item.item_id for item in manifest.included] == ["repo"]
    assert manifest.excluded == (("external", "forbidden"),)


def test_context_budget_uses_content_floor_not_only_declared_estimate() -> None:
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=1,
    )
    item = ContextItem("plan", SourceClass.APPROVED_PLAN, "x" * 100, 100, 100, 0)

    with pytest.raises(ContextSelectionError, match="exceeds token budget"):
        select_context(need, (item,))
