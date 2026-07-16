"""CX2 (09-context-engineering.md §11) — activity recipe schema tests.

CX2's acceptance criteria: "activity마다 required/optional/forbidden과
budget이 있다." These tests verify the six recipes are internally
consistent and cover every ActivityKind. They do NOT substitute for the
Human review CX2 also requires — token budgets especially are first-draft
estimates (see activity_recipes.py's module docstring).
"""

from __future__ import annotations

import pytest

from agent_lab.context.activity_recipes import ACTIVITY_RECIPES, recipe_for
from agent_lab.context.recipe import ActivityKind, ContextItem, SourceClass, select_context

CRITIC_RECIPE = ACTIVITY_RECIPES[ActivityKind.CRITIC]


def test_every_activity_kind_has_a_recipe() -> None:
    assert set(ACTIVITY_RECIPES) == set(ActivityKind)


@pytest.mark.parametrize("activity", list(ActivityKind))
def test_recipe_sources_do_not_overlap_across_required_optional_forbidden(activity: ActivityKind) -> None:
    need = recipe_for(activity)
    assert not (need.required_sources & need.optional_sources), f"{activity}: required/optional overlap"
    assert not (need.required_sources & need.forbidden_sources), f"{activity}: required/forbidden overlap"
    assert not (need.optional_sources & need.forbidden_sources), f"{activity}: optional/forbidden overlap"


@pytest.mark.parametrize("activity", list(ActivityKind))
def test_recipe_has_at_least_one_required_source_and_positive_budget(activity: ActivityKind) -> None:
    need = recipe_for(activity)
    assert need.required_sources, f"{activity}: no required sources"
    assert need.token_budget > 0, f"{activity}: non-positive token budget"


def test_critic_forbids_agent_opinion_to_keep_self_evaluation_out() -> None:
    """§6.3: '독립적 rubric' — the producing agent's own opinion must not
    reach the critic as evidence."""
    assert SourceClass.AGENT_OPINION in CRITIC_RECIPE.forbidden_sources


@pytest.mark.parametrize("activity", list(ActivityKind))
def test_every_activity_requires_system_invariant(activity: ActivityKind) -> None:
    """2026-07-16 review — clarify/repair were missing SYSTEM_INVARIANT even
    though every activity operates inside the same always-on Human gate/
    security/worktree boundaries. Now universal across all six recipes."""
    assert SourceClass.SYSTEM_INVARIANT in recipe_for(activity).required_sources


def test_each_recipe_is_satisfiable_with_one_item_per_required_source() -> None:
    """Smoke test: select_context() must not raise ContextSelectionError when
    every required source has at least one minimal item available. Content
    must differ per item — select_context() now dedupes identical content
    across sources (CX4 §7.2 review), so same-content fixtures here would
    collapse into one item and defeat the point of this test."""
    for activity, need in ACTIVITY_RECIPES.items():
        items = tuple(
            ContextItem(
                item_id=f"{activity.value}-{source.value}",
                source=source,
                content=f"x-{source.value}",
                authority=50,
                relevance=50,
                estimated_tokens=1,
            )
            for source in need.required_sources
        )
        manifest = select_context(need, items)
        assert set(item.source for item in manifest.included) == need.required_sources
