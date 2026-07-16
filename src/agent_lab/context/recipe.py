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
REDACTED_SECURITY_LABELS: frozenset[str] = frozenset({"secret", "credential", "pii"})
REDACTED_CONTENT_PLACEHOLDER = "[REDACTED]"


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


@dataclass(frozen=True, slots=True)
class ContextManifest:
    activity: ActivityKind
    included: tuple[ContextItem, ...]
    excluded: tuple[str, ...]
    total_tokens: int
    redacted: tuple[str, ...] = ()
    """item_ids whose content was replaced with REDACTED_CONTENT_PLACEHOLDER
    before inclusion — still present (provenance preserved), never raw."""


def _rank(item: ContextItem, required: frozenset[SourceClass]) -> tuple[int, int, int, str]:
    return (0 if item.source in required else 1, -item.authority, -item.relevance, item.item_id)


def _redact_if_needed(item: ContextItem) -> tuple[ContextItem, bool]:
    """CX3 — secret/credential/pii content must never reach a built manifest raw."""
    if item.security_label not in REDACTED_SECURITY_LABELS or item.content == REDACTED_CONTENT_PLACEHOLDER:
        return item, False
    return replace(item, content=REDACTED_CONTENT_PLACEHOLDER, estimated_tokens=1), True


def select_context(need: ContextNeed, items: tuple[ContextItem, ...]) -> ContextManifest:
    if need.token_budget < 0:
        raise ContextSelectionError("token budget must not be negative")
    allowed = need.required_sources | need.optional_sources
    candidates: list[ContextItem] = []
    excluded: list[str] = []
    redacted_ids: set[str] = set()
    for raw_item in items:
        item, was_redacted = _redact_if_needed(raw_item)
        if was_redacted:
            redacted_ids.add(item.item_id)
        if item.source in need.forbidden_sources or item.source not in allowed or not item.trusted:
            excluded.append(item.item_id)
        else:
            candidates.append(item)
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
    )


def manifest_provenance_gaps(manifest: ContextManifest) -> tuple[str, ...]:
    """CX3 acceptance criteria: '모든 included item에 source ref와 reason이 있다'.

    Returns item_ids in the manifest with no provenance recorded — callers
    decide whether that's a hard error or a warning; select_context() itself
    stays permissive so synthetic/test data doesn't need provenance filled in.
    """
    return tuple(item.item_id for item in manifest.included if not item.provenance.strip())
