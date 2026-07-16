"""CX5-adjacent §7.2 trim steps 3-6 (09-context-engineering.md §11 CX4/CX5).

`select_context()` already implements §7.2's first two trim steps (exact-
duplicate removal, low-authority/relevance exclusion) and its seventh
("그래도 초과하면 ... 명시적 context overflow 실패" — a still-too-large required
item raises `ContextSelectionError`, never gets silently dropped). Steps 3-6
are real content compression — the selector's own docstring calls this "out
of scope for a pure selector operating on already-built ContextItems." This
module is that missing piece, kept in a separate file for the same reason
`recipe.py` stayed a pure selector: compression is a different kind of
operation (lossy content transformation) from selection (choosing among
already-built items), and mixing them would make `select_context()` harder
to reason about and test.

Design mirrors `context/adapters.py`: every compression function takes
ALREADY-COMPUTED replacement data (a rendered summary, a pre-resolved symbol
snippet, an artifact ref string) rather than performing extraction/
summarization itself. Real transcript/required-item summarization needs
either an LLM call or a domain-specific heuristic — neither belongs in a
module that must stay testable with synthetic data and mock-only per this
repo's test policy (CLAUDE.md: "테스트: mock-only, 실 LLM CI 금지"). The
mechanical step this module DOES own: reshaping compressed content into a
smaller `ContextItem` that preserves what §7.3 requires (source refs,
decisions, unresolved questions, numeric constraints, must-not) and wiring
steps 3-6 around `select_context()` in the trim priority order §7.2
specifies.

§7.2's closing line — "system constraint와 현재 Human intent를 조용히 trim하지
않는다" — is honored by construction: every compression function REPLACES an
item with a smaller one (still present, with provenance noting it was
compressed), it never deletes an item outright. Silent, untraceable removal
only ever happens via `select_context()`'s own `excluded`/`unresolved_
conflicts` bookkeeping, which already records a reason for every exclusion.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from agent_lab.context.recipe import (
    ContextItem,
    ContextManifest,
    ContextNeed,
    estimate_tokens,
    select_context,
)


@dataclass(frozen=True, slots=True)
class StructuredSummary:
    """§7.3's compression-quality contract, as data: whatever process
    produced this (an LLM call, a rule-based extractor) must have preserved
    decisions, unresolved questions, numeric constraints, must-not
    directives, and refs back to the original content — this dataclass is
    the checklist made concrete, not an implementation of the extraction
    itself."""

    decisions: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    numeric_constraints: tuple[str, ...] = ()
    must_not: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def render(self) -> str:
        sections: list[tuple[str, tuple[str, ...]]] = [
            ("결정", self.decisions),
            ("미해결 질문", self.unresolved_questions),
            ("수치 제약", self.numeric_constraints),
            ("금지사항", self.must_not),
            ("원문 참조", self.source_refs),
        ]
        lines: list[str] = []
        for label, values in sections:
            if not values:
                continue
            lines.append(f"[{label}]")
            lines.extend(f"- {value}" for value in values)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class SymbolSnippet:
    """One symbol-graph/repo-map hit — already resolved by whatever tool
    does that resolution (out of this module's scope); this is just the
    shape `compress_repo_tree_to_symbol_snippets` expects."""

    symbol: str
    file_path: str
    snippet: str


def compress_tool_output_to_artifact_ref(
    item: ContextItem,
    *,
    artifact_ref: str,
    excerpt_chars: int = 400,
) -> ContextItem:
    """§7.2 step 3 — a large tool-output item replaced by a bounded head+tail
    excerpt plus a ref to the full artifact. Purely mechanical: the excerpt
    is a literal substring of the original content, never a paraphrase, so
    this step alone can't misrepresent what a tool actually returned.
    Returns the item unchanged if it's already within `excerpt_chars` —
    nothing to compress."""
    content = item.content
    if len(content) <= excerpt_chars:
        return item
    half = max(1, excerpt_chars // 2)
    excerpt = f"{content[:half]}\n…[truncated, full output: {artifact_ref}]…\n{content[-half:]}"
    provenance = f"{item.provenance} (compressed; full: {artifact_ref})" if item.provenance else artifact_ref
    return replace(item, content=excerpt, estimated_tokens=estimate_tokens(excerpt), provenance=provenance)


def compress_to_structured_summary(item: ContextItem, summary: StructuredSummary) -> ContextItem:
    """§7.2 steps 4 and 6 — replaces an item's content with an already-
    produced `StructuredSummary`'s rendering. Step 4 (stale conversation ->
    decision summary) and step 6 (required item -> structured summary) are
    mechanically the same transform; what differs is WHICH items a caller
    chooses to apply it to and in what trim priority (see
    `trim_to_budget`'s docstring) — not the code that does the replacing."""
    content = summary.render()
    provenance = f"{item.provenance} (compressed to structured summary)" if item.provenance else "structured summary"
    return replace(item, content=content, estimated_tokens=estimate_tokens(content), provenance=provenance)


def compress_repo_tree_to_symbol_snippets(item: ContextItem, snippets: list[SymbolSnippet]) -> list[ContextItem]:
    """§7.2 step 5 — a full repo-tree listing replaced by symbol-targeted
    snippets (already resolved by a symbol graph/repo-map tool; this
    function only reshapes the result, it doesn't resolve symbols itself).
    Returns a LIST, not one item: a repo tree can meaningfully decompose
    into several independent snippets, each individually rankable by
    select_context()'s own authority/relevance logic rather than one
    all-or-nothing blob. Each snippet gets its own item_id and no inherited
    conflict_key — snippets from different symbols don't compete for one
    slot the way the original tree item might have."""
    items: list[ContextItem] = []
    for index, snippet in enumerate(snippets):
        content = f"[{snippet.file_path} :: {snippet.symbol}]\n{snippet.snippet}"
        items.append(
            replace(
                item,
                item_id=f"{item.item_id}:symbol:{index}",
                content=content,
                estimated_tokens=estimate_tokens(content),
                provenance=f"{snippet.file_path} ({snippet.symbol})",
                conflict_key=None,
            )
        )
    return items


CompressFn = Callable[[ContextItem], "ContextItem | list[ContextItem]"]


def trim_to_budget(
    need: ContextNeed,
    items: tuple[ContextItem, ...],
    *,
    compressions: dict[str, tuple[int, CompressFn]] | None = None,
) -> ContextManifest:
    """§7.2 steps 3-6, wired around `select_context()` (which already
    implements steps 1-2 and step 7's explicit-failure guarantee).

    `compressions` maps an item_id to `(step, compress_fn)` — step must be
    one of 3/4/5/6, matching §7.2's ordering. Compression is deliberately
    the CALLER's decision, not automatic: only the caller (or a future CX8
    assembler) knows which item is tool output vs. stale transcript vs. repo
    tree vs. an oversized required item. This function owns only the
    mechanical wiring:

    - Step 6 entries are applied UNCONDITIONALLY before the first selection
      attempt. A required item registered at step 6 is, by construction,
      already known by the caller to need shrinking — waiting for
      select_context() to hard-fail on it first would just mean catching
      and re-deriving the same fact from an error message.
    - Steps 3/4/5 are applied PROGRESSIVELY: select once, then for any item
      excluded with reason "budget_overflow" that has a registered step-3
      compressor, apply it and re-select; repeat for step 4, then step 5.
      An item excluded for any other reason (forbidden/not_allowed/
      untrusted) is not a compression candidate — compressing it smaller
      wouldn't change why it was excluded.
    - If the item set still doesn't fit after all registered compressions
      run, the final `select_context()` call's `ContextSelectionError`
      propagates uncaught — that IS step 7 ("명시적 context overflow 실패"),
      already fully implemented by `select_context()` itself.
    """
    active = dict(compressions or {})
    current: dict[str, ContextItem] = {item.item_id: item for item in items}

    def _apply(item_id: str) -> None:
        _step, compress_fn = active[item_id]
        result = compress_fn(current[item_id])
        del current[item_id]
        for new_item in (result if isinstance(result, list) else [result]):
            current[new_item.item_id] = new_item

    for item_id, (step, _fn) in list(active.items()):
        if step == 6 and item_id in current:
            _apply(item_id)

    manifest = select_context(need, tuple(current.values()))
    for step in (3, 4, 5):
        budget_excluded_ids = {item_id for item_id, reason in manifest.excluded if reason == "budget_overflow"}
        step_ids = [
            item_id
            for item_id in budget_excluded_ids
            if item_id in active and active[item_id][0] == step
        ]
        if not step_ids:
            continue
        for item_id in step_ids:
            _apply(item_id)
        manifest = select_context(need, tuple(current.values()))
    return manifest
