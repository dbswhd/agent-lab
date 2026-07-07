"""S3a-0 — local capability inventory: installed-but-unused tool cards for RECALL.

See docs/N10-USER-LOOP-WISDOM-DRAFT.md §2 (S3a-0) and NORTH-STAR §1 Layer 1.
The 2026-07-06 usage audit found 54 installed Claude Code skills with only 3
actually invoked — S3's first bottleneck is RECALL (surfacing what's already
there), not discovery (crawling for more). This module turns
``plugin_discovery.discover_plugins()``'s existing local scan into "tool
cards" tagged with a topic_router category, and — like the existing
``_wisdom_note`` cross-session hint — appends a plain-text suggestion of
installed-but-unused capabilities to the advisor's rationale.

Not a new learning loop: this only widens RECALL's *input*, exactly per the
S1-first invariant ("S3는 S1 닫힌 후" is about new loops, not about reusing
already-installed capability metadata a turn already has on disk).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.run.state import RunStateLike

_AGENT_LAB_ROOT = Path(__file__).resolve().parents[2]

# Deterministic keyword tagging — no LLM call (same S1.5 discipline as
# feedback_advisor's sha1-seeded explore decision). Every card also always
# carries "standard" so general-purpose tools remain suggestible.
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "trading": ("trading", "quant", "backtest", "broker", "portfolio"),
    "deep": (
        "design",
        "architecture",
        "animation",
        "motion",
        "ui",
        "frontend",
        "refactor",
        "simplif",
    ),
    "critical": (
        "test",
        "debug",
        "security",
        "review",
        "quality",
        "accessibility",
        "audit",
    ),
    "quick": ("format", "lint", "rename", "cleanup"),
}


def _tag_categories(name: str, description: str) -> tuple[str, ...]:
    text = f"{name} {description}".lower()
    tags = {"standard"}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            tags.add(category)
    return tuple(sorted(tags))


def build_tool_cards(workspace: Path, *, mock: bool | None = None) -> list[dict[str, Any]]:
    """Local-inventory tool cards — plugin_discovery rows + category tags."""
    from agent_lab.plugin_discovery import discover_plugins

    plugins = discover_plugins(workspace, mock=mock).get("plugins") or []
    cards: list[dict[str, Any]] = []
    for row in plugins:
        name = str(row.get("name") or "")
        description = str(row.get("description") or "")
        cards.append(
            {
                "id": str(row.get("id") or ""),
                "name": name,
                "agent": str(row.get("agent") or ""),
                "kind": str(row.get("kind") or ""),
                "description": description,
                "categories": _tag_categories(name, description),
            }
        )
    return cards


def _explicitly_enabled_ids(run_meta: RunStateLike | None) -> set[str]:
    """Ids the session has explicitly chosen so far — NOT ``merge_session_allowlist``'s
    default-enabled backfill (every discovered row defaults ``enabled_default=True``,
    which would make almost everything look "already enabled" and nothing "unused")."""
    from agent_lab.plugin_discovery import read_agent_plugins

    stored = read_agent_plugins(run_meta)
    enabled: set[str] = set()
    for entry in stored.values():
        if isinstance(entry, dict) and isinstance(entry.get("enabled"), list):
            enabled.update(str(x) for x in entry["enabled"])
        elif isinstance(entry, list):
            enabled.update(str(x) for x in entry)
    return enabled


def unused_tool_cards_for_category(
    category: str,
    run_meta: RunStateLike | None,
    workspace: Path,
    *,
    mock: bool | None = None,
) -> list[dict[str, Any]]:
    """Cards tagged for ``category`` the session hasn't explicitly enabled yet."""
    enabled_ids = _explicitly_enabled_ids(run_meta)
    if "*" in enabled_ids:
        return []  # everything already allowed — nothing "unused" to suggest

    cards = build_tool_cards(workspace, mock=mock)
    return [c for c in cards if category in c["categories"] and c["id"] not in enabled_ids]


def tool_card_note(
    category: str,
    run_meta: RunStateLike | None,
    workspace: Path | None = None,
    *,
    limit: int = 3,
    mock: bool | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Short suggestion text + suggested ids, or ("", ()) — mirrors ``_wisdom_note``."""
    try:
        unused = unused_tool_cards_for_category(category, run_meta, workspace or _AGENT_LAB_ROOT, mock=mock)
    except Exception:
        return "", ()
    if not unused:
        return "", ()
    picked = unused[:limit]
    names = [str(c["name"]) for c in picked]
    ids = tuple(str(c["id"]) for c in picked)
    return "; ".join(names), ids


__all__ = [
    "build_tool_cards",
    "unused_tool_cards_for_category",
    "tool_card_note",
]
