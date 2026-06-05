"""Deterministic discuss harvest → Human Inbox question items (M3).

No LLM Facilitator, no options — refs + excerpt only. Mirrors
``room_objections.harvest_objections_from_turn``: operates on the in-memory
``run_meta`` dict (the caller persists it), so it never races the wholesale
run.json write that follows the turn-harvest block in ``room.py``.

Sources (RFC §5.4 / §5.5, 1단 deterministic harvest):
- envelope ``CHALLENGE`` / ``AMEND`` in the current turn  → ``T-Q1``
- ``plan.md`` OPEN bullets                               → ``T-Q2``

Options synthesis (FORK + Facilitator) is **M4** — not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from typing import Any

from agent_lab.human_inbox import (
    append_inbox_item,
    inbox_items,
    new_inbox_item,
)

_AGENT_IDS = frozenset({"cursor", "codex", "claude"})
_HARVEST_ACTS = frozenset({"CHALLENGE", "AMEND"})
_MAX_ITEMS = 3
_EXCERPT_CHARS = 240
_PROMPT_CHARS = 160


@dataclass(frozen=True)
class InboxQuestionCandidate:
    """A deterministic harvest hit — prompt + supporting refs/excerpt, no options."""

    prompt: str
    excerpt: str
    refs: tuple[str, ...]
    trigger: str
    harvest_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "excerpt": self.excerpt,
            "refs": list(self.refs),
            "trigger": self.trigger,
            "harvest_key": self.harvest_key,
        }


def _fingerprint(*parts: str) -> str:
    raw = "|".join((p or "").strip().lower() for p in parts)
    return "qh-" + sha1(raw.encode("utf-8")).hexdigest()[:12]


def _turn_messages(messages: list[Any]) -> list[Any]:
    """Slice messages after the last Human ``user`` message (current turn only)."""
    last_user = -1
    for i, m in enumerate(messages):
        if getattr(m, "role", None) == "user":
            last_user = i
    return messages[last_user + 1 :] if last_user >= 0 else list(messages)


def _envelope_dict(m: Any) -> dict[str, Any] | None:
    env = getattr(m, "envelope", None)
    if isinstance(env, dict):
        return env
    from agent_lab.agent_envelope import parse_agent_response

    parsed = parse_agent_response(getattr(m, "content", "") or "")
    return parsed.envelope.to_dict() if parsed.envelope else None


def _challenge_amend_candidates(messages: list[Any]) -> list[InboxQuestionCandidate]:
    from agent_lab.agent_envelope import envelope_act

    out: list[InboxQuestionCandidate] = []
    for m in _turn_messages(messages):
        if getattr(m, "role", None) != "agent":
            continue
        agent = str(getattr(m, "agent", "") or "").strip().lower()
        if agent not in _AGENT_IDS:
            continue
        env = _envelope_dict(m)
        if not env:
            continue
        act = envelope_act(env)
        if act not in _HARVEST_ACTS:
            continue
        message = str(env.get("message") or getattr(m, "content", "") or "").strip()
        if not message:
            continue
        refs = tuple(
            str(r).strip() for r in (env.get("refs") or []) if str(r).strip()
        )
        out.append(
            InboxQuestionCandidate(
                prompt=f"{agent} {act}: {message[:_PROMPT_CHARS]}",
                excerpt=message[:_EXCERPT_CHARS],
                refs=refs,
                trigger="T-Q1",
                harvest_key=_fingerprint(agent, act, message[:120]),
            )
        )
    return out


def _plan_open_candidates(plan_md: str) -> list[InboxQuestionCandidate]:
    if not (plan_md or "").strip():
        return []
    from agent_lab.room_context import extract_open_bullets

    out: list[InboxQuestionCandidate] = []
    for bullet in extract_open_bullets(plan_md):
        text = (bullet or "").strip()
        if not text:
            continue
        out.append(
            InboxQuestionCandidate(
                prompt=f"미결: {text[:_PROMPT_CHARS]}",
                excerpt=text[:_EXCERPT_CHARS],
                refs=("plan.md",),
                trigger="T-Q2",
                harvest_key=_fingerprint("plan-open", text[:120]),
            )
        )
    return out


def harvest_question_candidates(
    messages: list[Any],
    *,
    plan_md: str = "",
) -> list[InboxQuestionCandidate]:
    """Pure deterministic harvest — no I/O, no LLM, no options. Deduped + capped."""
    raw = _challenge_amend_candidates(messages) + _plan_open_candidates(plan_md)
    seen: set[str] = set()
    out: list[InboxQuestionCandidate] = []
    for c in raw:
        if c.harvest_key in seen:
            continue
        seen.add(c.harvest_key)
        out.append(c)
    return out[:_MAX_ITEMS]


def _existing_harvest_keys(run: dict[str, Any]) -> set[str]:
    return {
        str(item.get("harvest_key"))
        for item in inbox_items(run)
        if item.get("harvest_key")
    }


def harvest_discuss_questions(
    run_meta: dict[str, Any],
    messages: list[Any],
    *,
    human_turn: int | None = None,
    plan_md: str = "",
    mode: str = "discuss",
) -> list[dict[str, Any]]:
    """Surface deterministic discuss questions into the in-memory ``run_meta`` (M3).

    - ``options=[]`` always; ``source="orchestrator"`` (M4 adds FORK options).
    - Idempotent: a candidate whose ``harvest_key`` already exists in the inbox
      (any status) is skipped, so a fork is surfaced once, not re-nagged each turn.
    - Caller persists ``run_meta``.

    Returns the items created this call.
    """
    if mode != "discuss":
        return []
    candidates = harvest_question_candidates(messages, plan_md=plan_md)
    if not candidates:
        return []
    existing = _existing_harvest_keys(run_meta)
    created: list[dict[str, Any]] = []
    for c in candidates:
        if c.harvest_key in existing:
            continue
        item = new_inbox_item(
            kind="question",
            source="orchestrator",
            prompt=c.prompt,
            options=[],
            summary=c.excerpt,
            context_ref=(c.refs[0] if c.refs else None),
            trigger=c.trigger,
            refs=list(c.refs),
            harvest_key=c.harvest_key,
            human_turn_id=human_turn,
        )
        append_inbox_item(run_meta, item)
        existing.add(c.harvest_key)
        created.append(item)
    return created
