from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


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


@dataclass(frozen=True, slots=True)
class ContextItem:
    item_id: str
    source: SourceClass
    content: str
    authority: int
    relevance: int
    estimated_tokens: int
    trusted: bool = True
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
    highest-priority one (§5 tier, then authority, then freshness string
    descending) and drops the rest as superseded — this is the '오래된 plan
    vs 최신 승인 plan: 오래된 plan 제외' rule. freshness must be lexicographically
    sortable (zero-padded revision numbers, ISO timestamps) for the tie-break
    to be meaningful; callers are responsible for that format."""


@dataclass(frozen=True, slots=True)
class ContextManifest:
    activity: ActivityKind
    included: tuple[ContextItem, ...]
    excluded: tuple[str, ...]
    total_tokens: int
    redacted: tuple[str, ...] = ()
    """item_ids whose content was replaced with REDACTED_CONTENT_PLACEHOLDER
    before inclusion — still present (provenance preserved), never raw."""
    superseded: tuple[str, ...] = ()
    """item_ids dropped before budget selection: lost a conflict_key priority
    contest (CX4 §5), or were an exact-content duplicate of a kept item
    (CX4 §7.2 trim step 1). Distinct from `excluded`, which is budget/
    not-allowed exclusion."""


def _rank(item: ContextItem, required: frozenset[SourceClass]) -> tuple[int, int, int, str]:
    return (0 if item.source in required else 1, -item.authority, -item.relevance, item.item_id)


def _redact_if_needed(item: ContextItem) -> tuple[ContextItem, bool]:
    """CX3 — secret/credential content must never reach a built manifest raw.
    PII is handled separately by a CX6 adapter (see REDACTED_SECURITY_LABELS)."""
    if item.security_label not in REDACTED_SECURITY_LABELS or item.content == REDACTED_CONTENT_PLACEHOLDER:
        return item, False
    return replace(item, content=REDACTED_CONTENT_PLACEHOLDER, estimated_tokens=1), True


def _pick_winner(group: list[ContextItem]) -> ContextItem:
    """CX4 — highest §5 tier wins, ties broken by authority, then freshness
    (lexicographically greatest — see ContextItem.conflict_key docstring),
    then relevance, then item_id. Multi-pass stable sort: least significant
    key first, so the last pass (tier) decides ties from all prior passes."""
    ordered = sorted(group, key=lambda item: item.item_id)
    ordered = sorted(ordered, key=lambda item: -item.relevance)
    ordered = sorted(ordered, key=lambda item: item.freshness or "", reverse=True)
    ordered = sorted(ordered, key=lambda item: -item.authority)
    ordered = sorted(ordered, key=lambda item: CONFLICT_TIER.get(item.source, 99))
    return ordered[0]


def _resolve_conflicts(candidates: list[ContextItem]) -> tuple[list[ContextItem], list[str]]:
    """CX4 §7.2 trim step 1 (exact duplicates) + §5 conflict resolution
    (same conflict_key = same fact/slot, only the winner survives)."""
    by_content: dict[tuple[SourceClass, str], list[ContextItem]] = {}
    content_passthrough: list[ContextItem] = []
    for item in candidates:
        # Redacted items all share REDACTED_CONTENT_PLACEHOLDER — grouping by
        # content would wrongly treat distinct secrets as duplicates of
        # each other. Each stays its own group; conflict_key still applies.
        if item.content == REDACTED_CONTENT_PLACEHOLDER:
            content_passthrough.append(item)
        else:
            by_content.setdefault((item.source, item.content), []).append(item)
    deduped: list[ContextItem] = list(content_passthrough)
    superseded: list[str] = []
    for group in by_content.values():
        winner = _pick_winner(group) if len(group) > 1 else group[0]
        deduped.append(winner)
        superseded.extend(item.item_id for item in group if item.item_id != winner.item_id)

    by_conflict_key: dict[str, list[ContextItem]] = {}
    conflict_key_passthrough: list[ContextItem] = []
    for item in deduped:
        if item.conflict_key is None:
            conflict_key_passthrough.append(item)
        else:
            by_conflict_key.setdefault(item.conflict_key, []).append(item)
    survivors = list(conflict_key_passthrough)
    for group in by_conflict_key.values():
        winner = _pick_winner(group) if len(group) > 1 else group[0]
        survivors.append(winner)
        superseded.extend(item.item_id for item in group if item.item_id != winner.item_id)
    return survivors, superseded


def select_context(need: ContextNeed, items: tuple[ContextItem, ...]) -> ContextManifest:
    if need.token_budget < 0:
        raise ContextSelectionError("token budget must not be negative")
    allowed = need.required_sources | need.optional_sources
    eligible: list[ContextItem] = []
    excluded: list[str] = []
    redacted_ids: set[str] = set()
    for raw_item in items:
        item, was_redacted = _redact_if_needed(raw_item)
        if was_redacted:
            redacted_ids.add(item.item_id)
        if item.source in need.forbidden_sources or item.source not in allowed or not item.trusted:
            excluded.append(item.item_id)
        else:
            eligible.append(item)
    candidates, superseded_ids = _resolve_conflicts(eligible)
    available_sources = {item.source for item in candidates}
    missing = sorted(source.value for source in need.required_sources - available_sources)
    if missing:
        raise ContextSelectionError(f"missing required sources: {', '.join(missing)}")
    included: list[ContextItem] = []
    total_tokens = 0
    for item in sorted(candidates, key=lambda candidate: _rank(candidate, need.required_sources)):
        content_floor = max(1, (len(item.content) + 3) // 4)
        next_total = total_tokens + max(content_floor, item.estimated_tokens)
        if item.source in need.required_sources and next_total > need.token_budget:
            raise ContextSelectionError(f"required context exceeds token budget: {item.item_id}")
        if next_total <= need.token_budget:
            included.append(item)
            total_tokens = next_total
        else:
            excluded.append(item.item_id)
    included_ids = {item.item_id for item in included}
    return ContextManifest(
        need.activity,
        tuple(included),
        tuple(sorted(excluded)),
        total_tokens,
        redacted=tuple(sorted(redacted_ids & included_ids)),
        superseded=tuple(sorted(superseded_ids)),
    )


def manifest_provenance_gaps(manifest: ContextManifest) -> tuple[str, ...]:
    """CX3 acceptance criteria: '모든 included item에 source ref와 reason이 있다'.

    Returns item_ids in the manifest with no provenance recorded — callers
    decide whether that's a hard error or a warning; select_context() itself
    stays permissive so synthetic/test data doesn't need provenance filled in.
    """
    return tuple(item.item_id for item in manifest.included if not item.provenance.strip())
