from __future__ import annotations

from dataclasses import dataclass
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
    EXTERNAL_CONTENT = "external_content"


class ContextSelectionError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    def __str__(self) -> str:
        return self.reason


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


@dataclass(frozen=True, slots=True)
class ContextManifest:
    activity: ActivityKind
    included: tuple[ContextItem, ...]
    excluded: tuple[str, ...]
    total_tokens: int


def _rank(item: ContextItem, required: frozenset[SourceClass]) -> tuple[int, int, int, str]:
    return (0 if item.source in required else 1, -item.authority, -item.relevance, item.item_id)


def select_context(need: ContextNeed, items: tuple[ContextItem, ...]) -> ContextManifest:
    if need.token_budget < 0:
        raise ContextSelectionError("token budget must not be negative")
    allowed = need.required_sources | need.optional_sources
    candidates: list[ContextItem] = []
    excluded: list[str] = []
    for item in items:
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
    return ContextManifest(need.activity, tuple(included), tuple(sorted(excluded)), total_tokens)
