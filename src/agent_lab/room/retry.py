"""Partial-turn failed-agent retry.

When a room turn ends ``partial`` (some agents replied, some errored), re-invoke
ONLY the failed agents within the SAME human turn — preserving the successful
replies and the human_turn count — instead of re-running the whole turn. The
retried agent sees the human message plus the successful peers' replies as
this-turn context. A successful retry supersedes the agent's earlier error so
the turn status recomputes from ``partial`` to ``completed``.

Restricted to non-consensus discuss/team turns for now; consensus/verified
turns are rejected (their anchor/endorse semantics need separate handling).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.room._typing import as_agent_ids
from agent_lab.room.messages import (
    ChatMessage,
    _agent_turn_summary,
    _human_turn_count,
    _now,
    _turn_status_from_replies,
)

# Turn profiles whose consensus/verify semantics are out of scope for v1 retry.
_CONSENSUS_PROFILES = frozenset({"verified", "specialist", "loop", "review", "free"})


class RetryError(Exception):
    """Retry precondition failure; ``code`` maps to an HTTP status at the router."""

    def __init__(self, message: str, *, code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _is_consensus_turn(run_meta: RunStateLike | None) -> bool:
    rm = run_meta or {}
    if str(rm.get("turn_profile") or "").strip().lower() in _CONSENSUS_PROFILES:
        return True
    if str(rm.get("plan_intent") or "").strip().lower() == "loop":
        return True
    if str(rm.get("loop_topology") or "").strip().lower() in {"verified", "specialist"}:
        return True
    return False


def _last_user_index(messages: list[ChatMessage]) -> int:
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user":
            return i
    return -1


def retry_failed_agents(
    folder: Path,
    *,
    agents: list[str] | None = None,
    on_event: Any = None,
    permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Re-invoke the last turn's failed agents, preserving successful replies.

    Returns a summary {status, retried, succeeded, failed_agents, human_turn}.
    Raises RetryError(code=409|422) when the last turn is not partial or is a
    consensus/verified turn.
    """
    from agent_lab.room.parallel_rounds import run_agent_rounds
    from agent_lab.room.session_persist import _session_context, load_session_messages
    from agent_lab.run.meta import patch_run_meta

    plan_md, run_meta = _session_context(folder)
    messages = load_session_messages(folder)
    if not messages:
        raise RetryError("session has no turns to retry", code=409)

    last_user = _last_user_index(messages)
    turn = messages[last_user + 1 :] if last_user >= 0 else list(messages)
    status = _turn_status_from_replies(turn, cancelled=False)
    if status != "partial":
        raise RetryError(f"last turn is '{status}', not 'partial' — nothing to retry", code=409)
    if _is_consensus_turn(run_meta):
        raise RetryError("partial retry is not supported for consensus/verified turns yet", code=422)

    summary = _agent_turn_summary(turn)
    failed = summary["failed_agents"]
    succeeded = set(summary["succeeded_agents"])
    requested = {a.strip().lower() for a in agents} if agents else None
    subset = [a for a in failed if a not in succeeded and (requested is None or a in requested)]
    human_turn = _human_turn_count(messages)
    if not subset:
        # idempotent no-op: nothing left to retry for the requested agents
        return {
            "status": status,
            "retried": [],
            "succeeded": sorted(succeeded),
            "failed_agents": failed,
            "human_turn": human_turn,
        }

    topic = str(run_meta.get("topic") or "").strip()
    if not topic:
        topic_file = folder / "topic.txt"
        topic = topic_file.read_text(encoding="utf-8").strip() if topic_file.is_file() else ""

    context_log: list[dict[str, Any]] = []
    replies = run_agent_rounds(
        topic,
        messages,
        agents=as_agent_ids(subset),
        parallel_rounds=1,
        on_event=on_event,
        permissions=permissions or {},
        human_turn_index=max(0, human_turn - 1),
        plan_md=plan_md,
        run_meta=run_meta,
        context_log=context_log,
    )

    retried_set = set(subset)
    # Supersede the current turn's error markers for retried agents; their fresh
    # reply/error below is the authoritative latest outcome. Successful peer
    # replies and other turns are left untouched.
    kept: list[ChatMessage] = [
        m for i, m in enumerate(messages) if not (i > last_user and m.role == "system" and m.agent in retried_set)
    ]
    for reply in replies:
        reply.retry_of_turn = human_turn
    kept.extend(replies)

    chat_path = folder / "chat.jsonl"
    with chat_path.open("w", encoding="utf-8") as fh:
        for m in kept:
            fh.write(json.dumps(m.to_dict(), ensure_ascii=False) + "\n")

    now_succeeded = sorted({str(r.agent) for r in replies if r.role == "agent" and r.agent})

    def _record(run: dict[str, Any]) -> dict[str, Any]:
        history = list(run.get("retry_history") or [])
        history.append({"turn": human_turn, "agents": subset, "succeeded": now_succeeded, "ts": _now()})
        run["retry_history"] = history
        return run

    patch_run_meta(folder, _record)

    new_turn = kept[_last_user_index(kept) + 1 :]
    new_summary = _agent_turn_summary(new_turn)
    return {
        "status": _turn_status_from_replies(new_turn, cancelled=False),
        "retried": subset,
        "succeeded": now_succeeded,
        "failed_agents": new_summary["failed_agents"],
        "human_turn": human_turn,
    }
