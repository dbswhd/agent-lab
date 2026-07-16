from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from functools import cmp_to_key


class ActivityKind(StrEnum):
    CLARIFY = "clarify"
    PLAN = "plan"
    CRITIC = "critic"
    EXECUTE = "execute"
    REPAIR = "repair"
    SCRIBE = "scribe"


class SourceClass(StrEnum):
    SYSTEM_INVARIANT = "system_invariant"
    HUMAN_INTENT = "human_intent"
    APPROVED_PLAN = "approved_plan"
    RUNTIME_STATE = "runtime_state"
    EVIDENCE = "evidence"
    PROJECT_DOC = "project_doc"
    REPO_CONTEXT = "repo_context"
    EPISODE = "episode"
    SEMANTIC_MEMORY = "semantic_memory"
    AGENT_OPINION = "agent_opinion"
    EXTERNAL_CONTENT = "external_content"


class ContextSelectionError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    def __str__(self) -> str:
        return self.reason


# CX3 — matches the security_label vocabulary already used for message
# envelopes (docs/redesign-2026-07/08-collaboration-messaging.md §9).
SECURITY_LABELS: frozenset[str] = frozenset({"public", "project", "secret", "credential", "pii"})
# Labels whose raw content must never appear in a built manifest (CX3
# acceptance criteria: "manifest에 secret 원문이 없다"). Pattern-based secret
# scanning inside otherwise-public content is out of scope here — see
# docs/redesign-2026-07/09-context-engineering.md §8, CX6 territory.
#
# 2026-07-16 review: "pii" was removed from this set. Destructively redacting
# PII to a placeholder breaks task utility that needs the real value (e.g.
# "email the user") — CX3's own acceptance criteria only names "secret", not
# PII. Real PII handling is a CX6 adapter concern: stable pseudonymization/
# tokenization (PERSON_1, EMAIL_1, ...) via a persistent token registry, which
# preserves referential integrity and rehydration — something a stateless
# select_context() call can't provide. Until CX6 ships, pii-labeled content
# passes through select_context() unredacted; that's a known, accepted gap,
# not a silent guarantee.
REDACTED_SECURITY_LABELS: frozenset[str] = frozenset({"secret", "credential"})
REDACTED_CONTENT_PLACEHOLDER = "[REDACTED]"

# 2026-07-16 review #5 — sources whose content wasn't produced by this system
# and needs the untrusted-by-default posture 09-context-engineering.md §8
# calls for ("external/tool content는 <untrusted_content> 같은 명시적 data
# boundary로 전달"). Deliberately doesn't include AGENT_OPINION: a peer Room
# agent's proposal isn't an injection-safety concern the way raw web/MCP/tool
# text is — its lower weight is already expressed via tier 6 + low authority,
# not the trust flag. Only applies when the caller doesn't pass `trusted`
# explicitly (see ContextItem.__post_init__).
DEFAULT_UNTRUSTED_SOURCES: frozenset[SourceClass] = frozenset({SourceClass.EXTERNAL_CONTENT})

# CX4 — conflict priority tiers, docs/redesign-2026-07/09-context-engineering.md
# §5 "충돌 우선순위" (1~7, lower tier wins). REPO_CONTEXT isn't named explicitly
# in §5's list.
#
# 2026-07-16 review: moved from tier 3 (alongside RUNTIME_STATE/EVIDENCE) to
# tier 4 (alongside PROJECT_DOC). At tier 3, a stale repo snippet could win a
# conflict against genuinely current RUNTIME_STATE/EVIDENCE on an authority/
# freshness tie-break — repo content is commit-bound and can lag behind live
# runtime fact, so it shouldn't contend at the same tier.
CONFLICT_TIER: dict[SourceClass, int] = {
    SourceClass.SYSTEM_INVARIANT: 0,
    SourceClass.HUMAN_INTENT: 1,
    SourceClass.APPROVED_PLAN: 2,
    SourceClass.RUNTIME_STATE: 3,
    SourceClass.EVIDENCE: 3,
    SourceClass.PROJECT_DOC: 4,
    SourceClass.REPO_CONTEXT: 4,
    SourceClass.SEMANTIC_MEMORY: 5,
    SourceClass.EPISODE: 5,
    SourceClass.AGENT_OPINION: 6,
    SourceClass.EXTERNAL_CONTENT: 6,
}


@dataclass(frozen=True, slots=True)
class ContextNeed:
    activity: ActivityKind
    required_sources: frozenset[SourceClass]
    optional_sources: frozenset[SourceClass]
    forbidden_sources: frozenset[SourceClass]
    token_budget: int

    def __post_init__(self) -> None:
        # 2026-07-16 review #4 — a source that's both required and forbidden
        # (or optional and forbidden) is an impossible recipe: select_context()
        # excludes it as forbidden before the required-coverage check ever
        # runs, so it fails with a misleading "missing required sources"
        # instead of the real problem (the recipe itself is malformed). Catch
        # it at recipe-construction time instead of at selection time.
        req_forb = self.required_sources & self.forbidden_sources
        if req_forb:
            raise ValueError(f"required_sources and forbidden_sources overlap: {sorted(s.value for s in req_forb)}")
        opt_forb = self.optional_sources & self.forbidden_sources
        if opt_forb:
            raise ValueError(f"optional_sources and forbidden_sources overlap: {sorted(s.value for s in opt_forb)}")


@dataclass(frozen=True, slots=True)
class ContextItem:
    item_id: str
    source: SourceClass
    content: str
    authority: int
    relevance: int
    estimated_tokens: int
    trusted: bool | None = None
    """None means "use the source's default posture" — resolved in
    __post_init__ to False for DEFAULT_UNTRUSTED_SOURCES, True otherwise.
    Always a concrete bool once the item is constructed; pass an explicit
    True/False to override the source default."""
    # CX3 — provenance/freshness/security additions.
    provenance: str = ""
    """Source ref + reason a Human/reviewer can trace this item back to (CX3:
    "모든 included item에 source ref와 reason이 있다")."""
    freshness: str | None = None
    """Invalidation key per the source's row in 09-context-engineering.md §9
    (e.g. commit SHA for repo snippets, plan revision for plan content)."""
    security_label: str = "project"
    conflict_key: str | None = None
    """CX4 — items sharing a conflict_key represent the same fact/slot (e.g.
    two ContextItems for 'the current plan'). select_context() keeps only the
    highest-priority one (§5 tier, then authority, then — same-source ties
    only — freshness string descending, then relevance) and drops the rest as
    superseded — this is the '오래된 plan vs 최신 승인 plan: 오래된 plan 제외' rule.
    freshness must be lexicographically sortable (zero-padded revision
    numbers, ISO timestamps) for the tie-break to be meaningful; callers are
    responsible for that format. Cross-source ties (e.g. RUNTIME_STATE vs
    EVIDENCE, both tier 3) never compare freshness — different sources use
    incompatible formats, so authority/relevance decide instead. An empty
    string is treated as "no conflict_key" the same as None — see
    _resolve_conflicts, which would otherwise group all empty-key items
    together as if they were one contested fact."""

    def __post_init__(self) -> None:
        # 2026-07-16 review #1 — fail closed on an unrecognized security_label
        # instead of silently treating it as un-redactable. A typo'd label
        # ("secrt") would otherwise pass raw secret content straight through
        # _redact_if_needed, defeating CX3's "manifest에 secret 원문이 없다"
        # guarantee without any error.
        if self.security_label not in SECURITY_LABELS:
            raise ValueError(f"unknown security_label: {self.security_label!r} (expected one of {sorted(SECURITY_LABELS)})")
        if self.trusted is None:
            object.__setattr__(self, "trusted", self.source not in DEFAULT_UNTRUSTED_SOURCES)


EXCLUDE_REASONS: frozenset[str] = frozenset({"forbidden", "not_allowed", "untrusted", "budget_overflow"})


@dataclass(frozen=True, slots=True)
class ContextManifest:
    activity: ActivityKind
    included: tuple[ContextItem, ...]
    excluded: tuple[tuple[str, str], ...]
    """(item_id, reason) pairs — reason is one of EXCLUDE_REASONS. 2026-07-16
    review #3: previously a flat item_id tuple that mixed four distinct
    causes (forbidden source, not required/optional, untrusted, didn't fit
    budget) with no way for a caller to tell them apart."""
    total_tokens: int
    redacted: tuple[str, ...] = ()
    """item_ids whose content was replaced with REDACTED_CONTENT_PLACEHOLDER
    before inclusion — still present (provenance preserved), never raw."""
    superseded: tuple[tuple[str, str], ...] = ()
    """(loser_item_id, winner_item_id) pairs — lost a conflict_key priority
    contest (CX4 §5) or were an exact-content duplicate of a kept item (CX4
    §7.2 trim step 1), with a clear single winner. Distinct from `excluded`
    (budget/not-allowed exclusion) and from `unresolved_conflicts` (no clear
    winner at all)."""
    unresolved_conflicts: tuple[tuple[str, ...], ...] = ()
    """2026-07-16 review #1 — groups of item_ids that were genuinely tied on
    every meaningful signal (tier, authority, same-source freshness,
    relevance — only item_id differed) when competing for the same
    conflict_key or exact-duplicate slot. None of a tied group's items are
    included, superseded, or attributed a winner — per 09-context-
    engineering.md §5 ("해결할 수 없는 충돌은 둘 다 prompt에 던지지 않고
    structured ambiguity 또는 Human decision으로 승격한다"), deciding a real
    contradiction by an arbitrary item_id comparison isn't resolution, it's
    silently picking one. Callers are responsible for actually escalating
    these (Human decision, re-ranking with better authority/freshness data,
    etc.) — select_context() only detects and reports them."""


def _rank(item: ContextItem, required: frozenset[SourceClass]) -> tuple[int, int, int, str]:
    return (0 if item.source in required else 1, -item.authority, -item.relevance, item.item_id)


def _redact_if_needed(item: ContextItem) -> tuple[ContextItem, bool]:
    """CX3 — secret/credential content must never reach a built manifest raw.
    PII is handled separately by a CX6 adapter (see REDACTED_SECURITY_LABELS)."""
    if item.security_label not in REDACTED_SECURITY_LABELS or item.content == REDACTED_CONTENT_PLACEHOLDER:
        return item, False
    return replace(item, content=REDACTED_CONTENT_PLACEHOLDER, estimated_tokens=1), True


def _compare_candidates_core(a: ContextItem, b: ContextItem) -> int:
    """CX4 conflict-winner ordering WITHOUT the item_id tiebreak: lower §5 tier
    wins, then higher authority, then — ONLY when both items share a source —
    greater freshness string, then higher relevance. Returns 0 when every
    meaningful signal is tied, which _resolve_group() treats as "genuinely
    unresolvable" rather than falling through to an arbitrary decision.

    2026-07-16 review: freshness is gated on same-source because different
    sources use incompatible freshness formats (commit SHA vs ISO timestamp
    vs plan revision — see ContextItem.freshness docstring); comparing them
    lexicographically across sources is deterministic but meaningless as a
    "which is newer" signal. Restricting the comparison to same-source ties
    keeps it meaningful without inventing a cross-format normalization.
    """
    tier_a, tier_b = CONFLICT_TIER.get(a.source, 99), CONFLICT_TIER.get(b.source, 99)
    if tier_a != tier_b:
        return -1 if tier_a < tier_b else 1
    if a.authority != b.authority:
        return -1 if a.authority > b.authority else 1
    if a.source == b.source:
        fa, fb = a.freshness or "", b.freshness or ""
        if fa != fb:
            return -1 if fa > fb else 1
    if a.relevance != b.relevance:
        return -1 if a.relevance > b.relevance else 1
    return 0


def _compare_candidates(a: ContextItem, b: ContextItem) -> int:
    """Total ordering for sorting a group: _compare_candidates_core, then
    lower item_id breaks ties for a *stable, deterministic sort order* only.
    Do not read a win on this final tiebreak as a real decision — see
    _resolve_group(), which checks _compare_candidates_core in isolation and
    escalates instead of trusting an item_id-only win."""
    core = _compare_candidates_core(a, b)
    if core != 0:
        return core
    if a.item_id != b.item_id:
        return -1 if a.item_id < b.item_id else 1
    return 0


def _cross_source_rank(item: ContextItem) -> tuple[int, int, int]:
    """Cross-source-safe rank for comparing candidates that may come from
    different sources: lower §5 tier wins, then higher authority, then higher
    relevance — as a plain key tuple, not a pairwise comparator.

    2026-07-16 review round 5 #2 — deliberately excludes freshness.
    _compare_candidates_core only compares freshness when both items share a
    source, which makes it a valid total order *within* one source but
    non-transitive across a group spanning multiple sources (e.g. same-source
    A beats C on freshness, but neither A nor C is comparable to a
    same-tier/authority/relevance item B from another source on freshness at
    all — sorting a mixed group directly by that comparator can rank B
    between A and C inconsistently). Because this key never touches
    freshness, plain tuple comparison is transitive by construction, so it's
    only ever used to rank ONE representative per source (see
    _resolve_group), after freshness has already done its job settling
    same-source competition."""
    return (CONFLICT_TIER.get(item.source, 99), -item.authority, -item.relevance)


def _resolve_group(
    group: list[ContextItem],
) -> tuple[ContextItem | None, list[tuple[str, str]], tuple[str, ...] | None]:
    """Rank a group of items competing for the same exact-content or
    conflict_key slot. Returns (winner, superseded[(loser_id, winner_id)],
    tied_group).

    2026-07-16 review round 5 #2 — resolved in two passes instead of one flat
    comparator sort, because a single comparator that gates freshness on
    "same source" is non-transitive once a group mixes sources (see
    _cross_source_rank's docstring for the concrete counterexample). Mixing
    sources into one sort could silently lose a same-source resolution (e.g.
    A beats C on freshness) whenever a third, cross-source item B happened to
    tie with both A and C on tier/authority/relevance — B has no business
    being compared to A/C on freshness at all, but a flat sort could still
    scramble their relative order.

    Pass 1 — per source: rank that source's own items with
    _compare_candidates (fully valid here; every pair in a single-source
    bucket satisfies the "same source" gate, so freshness is always
    meaningfully comparable). A source that can't settle its own internal tie
    contributes no single representative — its whole bucket rides through as
    one contender, unresolved internally.

    Pass 2 — across sources: rank each source's representative (or
    unresolved bucket) via _cross_source_rank (tier/authority/relevance only,
    transitive, freshness already spent in pass 1). A source's items that are
    strictly outranked here are superseded by the winner regardless of any
    unresolved detail elsewhere — domination on tier/authority/relevance
    doesn't depend on how an unrelated tie eventually resolves. If more than
    one source shares the best cross-source rank (or the sole occupant of
    that rank is itself an internally-ambiguous source), there is no single
    defensible winner: per 09-context-engineering.md §5 ("해결할 수 없는
    충돌은 ... structured ambiguity 또는 Human decision으로 승격한다"), that
    contested top rank is reported as `tied_group` rather than decided.
    """
    if len(group) == 1:
        return group[0], [], None

    by_source: dict[SourceClass, list[ContextItem]] = {}
    for item in group:
        by_source.setdefault(item.source, []).append(item)

    # Each contender is (cross_source_rank, representative_or_None, item_ids).
    # representative is None when that source's own items are internally
    # tied (couldn't settle even with freshness) — item_ids then names the
    # whole ambiguous bucket instead of a single winner.
    contenders: list[tuple[tuple[int, int, int], ContextItem | None, list[str]]] = []
    superseded: list[tuple[str, str]] = []
    for source_items in by_source.values():
        if len(source_items) == 1:
            item = source_items[0]
            contenders.append((_cross_source_rank(item), item, [item.item_id]))
            continue
        ordered = sorted(source_items, key=cmp_to_key(_compare_candidates))
        top = ordered[0]
        tied = [candidate for candidate in ordered if _compare_candidates_core(top, candidate) == 0]
        if len(tied) > 1:
            contenders.append((_cross_source_rank(top), None, [candidate.item_id for candidate in source_items]))
            continue
        contenders.append((_cross_source_rank(top), top, [top.item_id]))
        superseded.extend((loser.item_id, top.item_id) for loser in ordered[1:])

    best_rank = min(rank for rank, _representative, _ids in contenders)
    top_contenders = [c for c in contenders if c[0] == best_rank]
    other_contenders = [c for c in contenders if c[0] != best_rank]

    if len(top_contenders) == 1 and top_contenders[0][1] is not None:
        winner = top_contenders[0][1]
        for _rank, _representative, ids in other_contenders:
            superseded.extend((loser_id, winner.item_id) for loser_id in ids)
        return winner, superseded, None

    # No single clean winner at the top rank — either two-or-more sources
    # tie there, or the sole top-rank source is itself internally ambiguous.
    # Everything else is still strictly dominated regardless of how the top
    # rank's ambiguity would eventually resolve, so it supersedes cleanly;
    # attribute it to the lexicographically-first top-rank item_id purely as
    # a stable pointer, not as a claim that item specifically "won" — the
    # real winner among the top rank is exactly what's being escalated.
    unresolved_ids: list[str] = []
    for _rank, _representative, ids in top_contenders:
        unresolved_ids.extend(ids)
    pointer_id = min(unresolved_ids)
    for _rank, _representative, ids in other_contenders:
        superseded.extend((loser_id, pointer_id) for loser_id in ids)
    return None, superseded, tuple(sorted(unresolved_ids))


def _resolve_conflicts(
    candidates: list[ContextItem],
) -> tuple[list[ContextItem], list[tuple[str, str]], list[tuple[str, ...]]]:
    """CX4 §7.2 trim step 1 (exact duplicates) + §5 conflict resolution
    (same conflict_key = same fact/slot, only the winner survives).

    Returns (survivors, superseded[(loser_id, winner_id)], unresolved_groups).
    """
    # 2026-07-16 review #2 — content-dedup groups by (conflict_key, content),
    # not content alone. Two items that declare DIFFERENT explicit
    # conflict_keys are asserting "we are different facts" even if their text
    # happens to match (e.g. a plan-slot value and a config-slot value that
    # coincidentally read the same) — merging them here, before conflict_key
    # resolution even runs, would silently drop one fact's only representative.
    # Items sharing a conflict_key (or both lacking one) still dedup by exact
    # content as before; the higher-priority copy (via _resolve_group, same
    # rule as conflict_key resolution) survives.
    def _dedup_key(item: ContextItem) -> tuple[str, str]:
        return (item.conflict_key or "", item.content)

    by_content: dict[tuple[str, str], list[ContextItem]] = {}
    content_passthrough: list[ContextItem] = []
    for item in candidates:
        # Redacted items all share REDACTED_CONTENT_PLACEHOLDER — grouping by
        # content would wrongly treat distinct secrets as duplicates of
        # each other. Each stays its own group; conflict_key still applies.
        # Same reasoning for "" (2026-07-16 review #3): an empty file summary,
        # empty tool result, and empty spreadsheet cell are all legitimately
        # different items that happen to have no content — not duplicates.
        if item.content == REDACTED_CONTENT_PLACEHOLDER or item.content == "":
            content_passthrough.append(item)
        else:
            by_content.setdefault(_dedup_key(item), []).append(item)
    deduped: list[ContextItem] = list(content_passthrough)
    superseded: list[tuple[str, str]] = []
    unresolved: list[tuple[str, ...]] = []
    for group in by_content.values():
        winner, group_superseded, tied_group = _resolve_group(group)
        # Always merge superseded pairs, even when the group also produces a
        # tied_group: a source strictly dominated at the cross-source rank
        # (2026-07-16 review round 5 #2) supersedes cleanly regardless of
        # whether the top rank itself is ambiguous.
        superseded.extend(group_superseded)
        if tied_group is not None:
            unresolved.append(tied_group)
            continue
        assert winner is not None
        deduped.append(winner)

    by_conflict_key: dict[str, list[ContextItem]] = {}
    conflict_key_passthrough: list[ContextItem] = []
    for item in deduped:
        # 2026-07-16 review #2 — "" is treated as "no conflict_key", same as
        # None (see ContextItem.conflict_key docstring). Without this, every
        # item defaulted or set to "" would land in one dict entry and get
        # collapsed to a single survivor by _resolve_group, superseding
        # unrelated items that never meant to compete for the same slot.
        if not item.conflict_key:
            conflict_key_passthrough.append(item)
        else:
            by_conflict_key.setdefault(item.conflict_key, []).append(item)
    survivors = list(conflict_key_passthrough)
    for group in by_conflict_key.values():
        winner, group_superseded, tied_group = _resolve_group(group)
        superseded.extend(group_superseded)
        if tied_group is not None:
            unresolved.append(tied_group)
            continue
        assert winner is not None
        survivors.append(winner)
    return survivors, superseded, unresolved


def select_context(need: ContextNeed, items: tuple[ContextItem, ...]) -> ContextManifest:
    if need.token_budget < 0:
        raise ContextSelectionError("token budget must not be negative")
    # 2026-07-16 review #4 — reject duplicate item_ids up front. Downstream
    # bookkeeping (redacted_ids & included_ids, excluded/superseded id
    # matching) assumes item_id uniquely identifies an item; a duplicate would
    # let two distinct ContextItems silently share one identity in the
    # manifest with no way for a caller to tell them apart.
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for item in items:
        if item.item_id in seen_ids:
            duplicate_ids.add(item.item_id)
        seen_ids.add(item.item_id)
    if duplicate_ids:
        raise ContextSelectionError(f"duplicate item_id(s): {sorted(duplicate_ids)}")

    allowed = need.required_sources | need.optional_sources
    eligible: list[ContextItem] = []
    excluded: list[tuple[str, str]] = []
    redacted_ids: set[str] = set()
    for raw_item in items:
        item, was_redacted = _redact_if_needed(raw_item)
        if was_redacted:
            redacted_ids.add(item.item_id)
        if item.source in need.forbidden_sources:
            excluded.append((item.item_id, "forbidden"))
        elif item.source not in allowed:
            excluded.append((item.item_id, "not_allowed"))
        elif not item.trusted:
            excluded.append((item.item_id, "untrusted"))
        else:
            eligible.append(item)
    candidates, superseded_pairs, unresolved_conflicts = _resolve_conflicts(eligible)
    # 2026-07-16 review: coverage is checked against `eligible` (pre-conflict-
    # resolution), not `candidates`. A required source's sole item can lose a
    # conflict_key contest to a higher-tier item from a different source
    # representing the same fact — by design (a better carrier now speaks for
    # that fact) — and that shouldn't register as "missing".
    eligible_sources = {item.source for item in eligible}
    missing = sorted(source.value for source in need.required_sources - eligible_sources)
    if missing:
        raise ContextSelectionError(f"missing required sources: {', '.join(missing)}")
    # 2026-07-16 review round 5 #1 — a required source whose eligible item(s)
    # ended up entirely inside an unresolved tie (none of them made it into
    # `candidates`, cleanly superseded or otherwise) must NOT return
    # silently: unresolved_conflicts is an advisory field, and a caller that
    # doesn't inspect it would proceed with a required fact simply absent
    # from the manifest — violating CX3's "excluded required item은 오류로
    # 드러난다" and §12's "required가 목적에 맞게 들어간다". This is distinct
    # from the case above (a required source's item cleanly SUPERSEDED by a
    # different source's higher-priority representative of the same fact,
    # which is intentional and stays silent) — here nothing at all speaks for
    # the source, the resolution just couldn't decide who.
    candidate_sources = {item.source for item in candidates}
    unresolved_item_ids = {item_id for group in unresolved_conflicts for item_id in group}
    unresolved_required = sorted(
        source.value
        for source in need.required_sources - candidate_sources
        if any(item.item_id in unresolved_item_ids for item in eligible if item.source == source)
    )
    if unresolved_required:
        raise ContextSelectionError(f"required source unresolved: {', '.join(unresolved_required)}")
    included: list[ContextItem] = []
    total_tokens = 0
    satisfied_required: set[SourceClass] = set()
    for item in sorted(candidates, key=lambda candidate: _rank(candidate, need.required_sources)):
        # 2026-07-16 review round 5 #5 — the content-floor guard exists to
        # protect against a caller UNDER-declaring estimated_tokens for real
        # content. A redacted placeholder's content is exactly known (it's
        # always REDACTED_CONTENT_PLACEHOLDER), so the floor's protection
        # doesn't apply; without this exemption _redact_if_needed's
        # estimated_tokens=1 was always overridden by the placeholder's own
        # length-derived floor (dead code — REDACTED_CONTENT_PLACEHOLDER is
        # long enough that its floor is 3, never 1).
        if item.content == REDACTED_CONTENT_PLACEHOLDER:
            next_total = total_tokens + item.estimated_tokens
        else:
            content_floor = max(1, (len(item.content) + 3) // 4)
            next_total = total_tokens + max(content_floor, item.estimated_tokens)
        # 2026-07-16 review: only the FIRST (best, since candidates are sorted
        # required-first/authority-desc) item of a still-unsatisfied required
        # source can trip a hard failure. Extra items of an already-satisfied
        # required source that don't fit just get excluded like any optional
        # item — the requirement was already met.
        if (
            item.source in need.required_sources
            and item.source not in satisfied_required
            and next_total > need.token_budget
        ):
            raise ContextSelectionError(f"required context exceeds token budget: {item.item_id}")
        if next_total <= need.token_budget:
            included.append(item)
            total_tokens = next_total
            if item.source in need.required_sources:
                satisfied_required.add(item.source)
        else:
            excluded.append((item.item_id, "budget_overflow"))
    included_ids = {item.item_id for item in included}
    return ContextManifest(
        need.activity,
        tuple(included),
        tuple(sorted(excluded)),
        total_tokens,
        redacted=tuple(sorted(redacted_ids & included_ids)),
        superseded=tuple(sorted(superseded_pairs)),
        unresolved_conflicts=tuple(sorted(unresolved_conflicts)),
    )


def manifest_provenance_gaps(manifest: ContextManifest) -> tuple[str, ...]:
    """CX3 acceptance criteria: '모든 included item에 source ref와 reason이 있다'.

    Returns item_ids in the manifest with no provenance recorded — callers
    decide whether that's a hard error or a warning; select_context() itself
    stays permissive so synthetic/test data doesn't need provenance filled in.
    """
    return tuple(item.item_id for item in manifest.included if not item.provenance.strip())
