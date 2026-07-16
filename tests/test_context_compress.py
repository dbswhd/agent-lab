"""09-context-engineering.md §7.2 trim steps 3-6 (src/agent_lab/context/compress.py).

select_context() already implements steps 1-2 (exact-duplicate removal,
low-authority/relevance exclusion) and step 7 (explicit ContextSelectionError
when a required item still doesn't fit after everything else). This file
covers the four compression functions (steps 3-6) plus trim_to_budget's
wiring around select_context() for the progressive/unconditional split.
"""

from __future__ import annotations

import pytest

from agent_lab.context.compress import (
    StructuredSummary,
    SymbolSnippet,
    compress_repo_tree_to_symbol_snippets,
    compress_to_structured_summary,
    compress_tool_output_to_artifact_ref,
    trim_to_budget,
)
from agent_lab.context.recipe import (
    ActivityKind,
    ContextItem,
    ContextNeed,
    ContextSelectionError,
    SourceClass,
)


def test_structured_summary_render_only_includes_populated_sections() -> None:
    summary = StructuredSummary(decisions=("ship v2",), must_not=("don't touch auth",))
    rendered = summary.render()
    assert "[결정]" in rendered
    assert "- ship v2" in rendered
    assert "[금지사항]" in rendered
    assert "- don't touch auth" in rendered
    assert "[미해결 질문]" not in rendered
    assert "[수치 제약]" not in rendered
    assert "[원문 참조]" not in rendered


def test_structured_summary_render_empty_when_no_fields_set() -> None:
    assert StructuredSummary().render() == ""


def test_compress_tool_output_to_artifact_ref_truncates_and_keeps_ref() -> None:
    item = ContextItem(
        "tool-1", SourceClass.EVIDENCE, "x" * 1000, authority=50, relevance=50, estimated_tokens=250,
        provenance="tool call #1",
    )
    compressed = compress_tool_output_to_artifact_ref(item, artifact_ref="artifacts/tool-1.txt", excerpt_chars=100)
    assert len(compressed.content) < len(item.content)
    assert "artifacts/tool-1.txt" in compressed.content
    assert "artifacts/tool-1.txt" in compressed.provenance
    assert compressed.estimated_tokens < item.estimated_tokens
    assert compressed.item_id == item.item_id  # still traceable to the same item


def test_compress_tool_output_to_artifact_ref_is_a_noop_when_already_small() -> None:
    item = ContextItem("tool-2", SourceClass.EVIDENCE, "short", authority=50, relevance=50, estimated_tokens=2)
    compressed = compress_tool_output_to_artifact_ref(item, artifact_ref="ref", excerpt_chars=400)
    assert compressed == item


def test_compress_to_structured_summary_replaces_content_and_notes_provenance() -> None:
    item = ContextItem(
        "transcript-1", SourceClass.EPISODE, "a" * 500, authority=40, relevance=40, estimated_tokens=125,
        provenance="notepad.md",
    )
    summary = StructuredSummary(decisions=("use React",), source_refs=("notepad.md#L10",))
    compressed = compress_to_structured_summary(item, summary)
    assert "use React" in compressed.content
    assert "notepad.md#L10" in compressed.content
    assert compressed.provenance.startswith("notepad.md")
    assert compressed.estimated_tokens < item.estimated_tokens


def test_compress_repo_tree_to_symbol_snippets_produces_one_item_per_snippet() -> None:
    item = ContextItem(
        "repo_tree", SourceClass.REPO_CONTEXT, "[Repo tree]\n- src/\n- tests/",
        authority=60, relevance=60, estimated_tokens=20, conflict_key="repo-slot",
    )
    snippets = [
        SymbolSnippet(symbol="select_context", file_path="src/agent_lab/context/recipe.py", snippet="def select_context(...): ..."),
        SymbolSnippet(symbol="ContextItem", file_path="src/agent_lab/context/recipe.py", snippet="class ContextItem: ..."),
    ]
    items = compress_repo_tree_to_symbol_snippets(item, snippets)
    assert len(items) == 2
    assert items[0].item_id == "repo_tree:symbol:0"
    assert items[1].item_id == "repo_tree:symbol:1"
    assert all(i.source == SourceClass.REPO_CONTEXT for i in items)
    assert all(i.conflict_key is None for i in items)  # don't inherit the tree's slot
    assert "select_context" in items[0].content


def test_trim_to_budget_returns_selection_unchanged_when_nothing_needs_compressing() -> None:
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset({SourceClass.APPROVED_PLAN}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=1_000,
    )
    plan = ContextItem("plan", SourceClass.APPROVED_PLAN, "ship it", authority=100, relevance=100, estimated_tokens=4)
    manifest = trim_to_budget(need, (plan,))
    assert [item.item_id for item in manifest.included] == ["plan"]


def test_trim_to_budget_compresses_budget_overflow_items_at_step_3_and_retries() -> None:
    """A large EVIDENCE item would normally be excluded (budget_overflow);
    registering it as a step-3 tool-output compressor should let it survive
    the second selection pass, shrunk."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset(),
        optional_sources=frozenset({SourceClass.EVIDENCE}),
        forbidden_sources=frozenset(),
        token_budget=50,
    )
    big_tool_output = ContextItem(
        "tool-output", SourceClass.EVIDENCE, "y" * 800, authority=50, relevance=50, estimated_tokens=200,
    )

    def compressor(item: ContextItem) -> ContextItem:
        return compress_tool_output_to_artifact_ref(item, artifact_ref="artifacts/tool-output.txt", excerpt_chars=80)

    without_compression = trim_to_budget(need, (big_tool_output,))
    assert without_compression.included == ()
    assert ("tool-output", "budget_overflow") in without_compression.excluded

    with_compression = trim_to_budget(
        need, (big_tool_output,), compressions={"tool-output": (3, compressor)},
    )
    assert [item.item_id for item in with_compression.included] == ["tool-output"]


def test_trim_to_budget_applies_step_6_unconditionally_for_a_required_item() -> None:
    """A required item too large to fit raises ContextSelectionError from
    select_context() directly (never merely excluded, since required items
    get a hard failure not a soft exclude) -- a step-6 compressor must be
    applied BEFORE that first attempt, not after catching a failure."""
    need = ContextNeed(
        activity=ActivityKind.REPAIR,
        required_sources=frozenset({SourceClass.EVIDENCE}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=20,
    )
    oversized_required = ContextItem(
        "big-evidence", SourceClass.EVIDENCE, "z" * 400, authority=100, relevance=100, estimated_tokens=100,
        provenance="evidence.jsonl",
    )
    summary = StructuredSummary(must_not=("do not skip verification",), source_refs=("evidence.jsonl#12",))

    def compressor(item: ContextItem) -> ContextItem:
        return compress_to_structured_summary(item, summary)

    manifest = trim_to_budget(
        need, (oversized_required,), compressions={"big-evidence": (6, compressor)},
    )
    assert [item.item_id for item in manifest.included] == ["big-evidence"]
    assert "do not skip verification" in manifest.included[0].content


def test_trim_to_budget_still_raises_when_compression_is_not_enough() -> None:
    """§7.2 step 7 — if even after every registered compression the
    required content doesn't fit, select_context()'s own explicit failure
    propagates uncaught. Compression is not a silent-failure escape hatch."""
    need = ContextNeed(
        activity=ActivityKind.REPAIR,
        required_sources=frozenset({SourceClass.EVIDENCE}),
        optional_sources=frozenset(),
        forbidden_sources=frozenset(),
        token_budget=1,
    )
    oversized_required = ContextItem(
        "big-evidence", SourceClass.EVIDENCE, "z" * 400, authority=100, relevance=100, estimated_tokens=100,
    )
    summary = StructuredSummary(must_not=("still too big to fit in budget=1",))

    def compressor(item: ContextItem) -> ContextItem:
        return compress_to_structured_summary(item, summary)

    with pytest.raises(ContextSelectionError, match="exceeds token budget"):
        trim_to_budget(need, (oversized_required,), compressions={"big-evidence": (6, compressor)})


def test_trim_to_budget_leaves_non_budget_exclusions_uncompressed() -> None:
    """An item excluded for forbidden/not_allowed/untrusted reasons is not a
    compression candidate -- shrinking it wouldn't change why it was
    excluded, so a registered compressor for it must not even be tried."""
    need = ContextNeed(
        activity=ActivityKind.EXECUTE,
        required_sources=frozenset(),
        optional_sources=frozenset(),
        forbidden_sources=frozenset({SourceClass.EXTERNAL_CONTENT}),
        token_budget=1_000,
    )
    forbidden_item = ContextItem(
        "forbidden", SourceClass.EXTERNAL_CONTENT, "y" * 800, authority=50, relevance=50, estimated_tokens=200,
    )
    calls = {"count": 0}

    def compressor(item: ContextItem) -> ContextItem:
        calls["count"] += 1
        return compress_tool_output_to_artifact_ref(item, artifact_ref="ref", excerpt_chars=10)

    manifest = trim_to_budget(need, (forbidden_item,), compressions={"forbidden": (3, compressor)})
    assert calls["count"] == 0
    assert ("forbidden", "forbidden") in manifest.excluded
