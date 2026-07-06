"""Pure adapter bridging the clarity scoring engine (C) to the server clarifier (A).

This module is intentionally a *thin, pure* adapter:

* It performs NO storage writes (no run.json/patch_run_meta); the server clarifier (A)
  remains the sole owner of the durable ``clarifier_interview`` field.
* It has NO top-level imports of ``session_clarifier`` (A) or ``clarity`` (C); ``clarity`` is
  imported lazily inside functions, so the A → adapter → C edge can never form an import cycle
  (C never imports this module at top level either).

The clarity engine is always active: vague topics hold CLARIFY; anchored topics pass immediately
(regex short-circuit, no LLM call). The legacy engine env toggle is no longer read.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

#: Marks interviews built by the clarity engine so identity-aware persistence can tell
#: engine-sourced interviews apart from the static server-clarifier templates ("server").
ENGINE_SOURCE = "clarity_engine"


def _now_iso() -> str:
    # Deterministic under mock so engine-backed interviews are byte-reproducible in CI.
    if os.getenv("AGENT_LAB_MOCK_AGENTS"):
        return "1970-01-01T00:00:00+00:00"
    return datetime.now(timezone.utc).isoformat()


def engine_questions(
    text: str,
    *,
    agents: list[str] | None = None,
    max_q: int = 5,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """One-pass clarity scoring + question derivation.

    Returns ``(score_result, questions)`` from a SINGLE ``score_clarity`` pass so callers
    (A's builder and B's gate) never double-score. ``questions`` is empty when the task is
    anchored or already clear (clarity engine's anchor-skip / threshold short-circuit).
    """
    from agent_lab.clarity import lateral_questions_from_result, score_clarity

    result = score_clarity(text, agents=agents)
    questions = lateral_questions_from_result(result, max_q=max_q)
    return result, questions


def build_engine_interview(
    text: str,
    *,
    human_message_count: int = 0,
    plan_mode: bool = False,
    agents: list[str] | None = None,
    max_q: int = 5,
) -> dict[str, Any] | None:
    """Build an A-shaped v2 interview from clarity-engine questions, or ``None``.

    Returns ``None`` when the engine produces no questions (anchored / already-clear task),
    so the caller falls through to A's existing static behavior. The returned dict matches
    ``session_clarifier.build_clarifier_interview``'s public shape exactly, plus a ``source``
    marker and the engine's ``weakest`` dimension for observability.
    """
    text = (text or "").strip()
    if not text:
        return None
    result, questions = engine_questions(text, agents=agents, max_q=max_q)
    if not questions:
        return None
    from agent_lab.plan.clarify_options import attach_options_to_questions

    questions = attach_options_to_questions(questions[:max_q], topic=text)
    return {
        "version": 2,
        "plan_mode": plan_mode,
        "status": "pending",
        "source": ENGINE_SOURCE,
        "human_turn": human_message_count,
        "questions": questions[:max_q],
        "answers": {},
        "weakest": result.get("weakest"),
        "created_at": _now_iso(),
    }
