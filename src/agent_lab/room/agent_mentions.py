"""Parse ``@agent`` tokens in Human messages to target a roster subset."""

from __future__ import annotations

import re

from typing import Any

from agent_lab.agents.plugins import AGENT_IDS
from agent_lab.run.state import RunStateLike

_MENTION_RE = re.compile(r"(?<![A-Za-z0-9_-])@([a-zA-Z][a-zA-Z0-9_-]*)\b")

# Alternate spellings → canonical provider id (must still be in active pool).
_ALIASES: dict[str, str] = {
    "kimi-work": "kimi_work",
}

# Tokens that may map into the active pool via alias rules (e.g. @kimi → kimi_work).
_MENTION_VOCAB = frozenset({*(a.lower() for a in AGENT_IDS), *_ALIASES, "kimi", "kimi_work", "local"})


def _canonical_mention_token(raw: str, *, active: set[str]) -> str | None:
    token = raw.strip().lower().lstrip("@")
    if not token:
        return None
    token = _ALIASES.get(token, token)
    if token == "kimi":
        if "kimi_work" in active:
            return "kimi_work"
        if "kimi" in active:
            return "kimi"
        return None
    if token in active:
        return token
    return None


def parse_agent_mentions(text: str, active_pool: list[str]) -> list[str]:
    """Return ordered unique agent ids mentioned via ``@id`` in *text*."""
    active = {a.strip().lower() for a in active_pool if str(a).strip()}
    seen: list[str] = []
    for m in _MENTION_RE.finditer(text or ""):
        raw = m.group(1).strip().lower()
        if raw not in _MENTION_VOCAB:
            continue
        canon = _canonical_mention_token(raw, active=active)
        if canon and canon not in seen:
            seen.append(canon)
    return seen


def parse_explicit_mentions(text: str) -> list[str]:
    """Parse ``@agent`` tokens against the full provider vocabulary (ignores roster)."""
    active = {str(a).strip().lower() for a in AGENT_IDS if str(a).strip()}
    seen: list[str] = []
    for m in _MENTION_RE.finditer(text or ""):
        raw = m.group(1).strip().lower()
        if raw not in _MENTION_VOCAB:
            continue
        canon = _canonical_mention_token(raw, active=active)
        if canon and canon not in seen:
            seen.append(canon)
    return seen


def out_of_roster_mentions(text: str, roster_pool: list[str]) -> list[str]:
    """Explicit ``@agent`` targets that are valid providers but not in *roster_pool*."""
    pool = {str(a).strip().lower() for a in roster_pool if str(a).strip()}
    return [m for m in parse_explicit_mentions(text) if m not in pool]


def mention_not_in_roster_message(out_of_roster: list[str], roster_pool: list[str]) -> str:
    """Human-readable error when @-targets are absent from the session roster."""
    missing = ", ".join(f"@{a}" for a in out_of_roster)
    roster = ", ".join(str(a) for a in roster_pool if str(a).strip()) or "(empty)"
    return (
        f"{missing} is not in this session's agent roster ({roster}). Add them with /model or mention an active agent."
    )


def strip_agent_mentions(text: str) -> str:
    """Remove ``@agent`` tokens; collapse whitespace."""
    cleaned = _MENTION_RE.sub(" ", text or "")
    return " ".join(cleaned.split()).strip()


def apply_agent_mention_filter(
    body: str,
    active_agents: list[str],
    *,
    roster_pool: list[str] | None = None,
) -> tuple[list[str], str, list[str]]:
    """Filter roster when the Human message @-targets specific peers.

    Returns ``(agents, stripped_body, mention_targets)``. When no valid mention
    is found, returns the original roster and body unchanged.

    *roster_pool* is the Human-selected composition (before availability shrink).
    Explicit @-mentions resolve against it so ``@claude`` still routes to Claude
    when a transient health/usage filter dropped it from *active_agents*.
    """
    active = [str(a).strip().lower() for a in active_agents if str(a).strip()]
    pool_source = roster_pool if roster_pool is not None else active_agents
    pool = [str(a).strip().lower() for a in pool_source if str(a).strip()]
    if not pool:
        pool = active
    mentions = parse_agent_mentions(body, pool)
    if not mentions:
        return list(active_agents), body, []
    mention_set = set(mentions)
    filtered: list[str] = []
    seen: set[str] = set()
    for raw in pool_source:
        aid = str(raw).strip().lower()
        if not aid or aid not in mention_set or aid in seen:
            continue
        seen.add(aid)
        filtered.append(aid)
    if not filtered:
        return list(active_agents), body, []
    return filtered, strip_agent_mentions(body), mentions


def effective_invoke_agents(
    agents: list[Any] | None,
    run_meta: RunStateLike | None,
    *,
    fallback: list[Any] | None = None,
) -> list[str]:
    """Roster actually invoked this turn — respects ``run_meta._turn_target_agents``."""
    base = [str(a).strip().lower() for a in (agents or fallback or []) if str(a).strip()]
    if not isinstance(run_meta, dict):
        return base
    targets = run_meta.get("_turn_target_agents")
    if not isinstance(targets, list) or not targets:
        return base
    target_set = {str(t).strip().lower() for t in targets if str(t).strip()}
    if not target_set:
        return base
    filtered = [a for a in base if a in target_set]
    return filtered if filtered else base
