"""Partial-turn failed-agent retry.

When a room turn ends ``partial`` (some agents replied, some errored), re-invoke
ONLY the failed agents within the SAME human turn — preserving the successful
replies and the human_turn count — instead of re-running the whole turn. The
retried agent sees the human message plus the successful peers' replies as
this-turn context. A successful retry supersedes the agent's earlier error so
the turn status recomputes from ``partial`` to ``completed``.

Restricted to non-consensus discuss/team turns for now; consensus/verified
turns are rejected (their anchor/endorse semantics need separate handling).

C1 (diagnose-before-retry, docs/N10-USER-LOOP-WISDOM-DRAFT.md §4-C1): a retry
whose failure signature (failed agents + their error text) exactly matches the
signature that triggered the *previous* retry of this turn means the retry
didn't help — repeating it blind is a reflexive loop, not a fix. That case is
blocked (RetryError 409) and escalated to Human Inbox instead of silently
retrying again; the diagnosis one-liner rides in the error message so it
reaches the UI without a separate round trip (see room.py error surfacing).
"""

from __future__ import annotations

import hashlib
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


def _last_errors(turn: list[ChatMessage]) -> dict[str, str]:
    return {str(m.agent): m.content for m in turn if m.role == "system" and m.agent}


def _failure_signature(agents: list[str], errors: dict[str, str]) -> str:
    """Deterministic fingerprint of a failure — no LLM, matches S1.5 discipline."""
    payload = "|".join(f"{a}:{(errors.get(a) or '')[:200]}" for a in sorted(agents))
    return "sha1:" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def diagnosis_line(agents: list[str], errors: dict[str, str]) -> str:
    """One-line diagnosis summary — surfaced before/instead of a blind retry."""
    if not agents:
        return ""
    parts = []
    for a in agents:
        err = (errors.get(a) or "").strip().splitlines()[0] if errors.get(a) else "원인 불명"
        if len(err) > 100:
            err = err[:97] + "..."
        parts.append(f"{a}: {err}")
    return " · ".join(parts)


def _pending_retry_diagnosis(run_meta: RunStateLike, human_turn: int, signature: str) -> bool:
    for item in run_meta.get("human_inbox") or []:
        if not isinstance(item, dict) or item.get("status") != "pending":
            continue
        if item.get("kind") != "retry_diagnosis":
            continue
        refs = list(item.get("refs") or [])
        if refs[:2] == [str(human_turn), signature]:
            return True
    return False


def _escalate_retry_diagnosis(
    folder: Path, run_meta: RunStateLike, agents: list[str], human_turn: int, signature: str, diagnosis: str
) -> None:
    """Human Inbox escalation for a same-signature repeat failure (fail-open)."""
    try:
        from agent_lab.human_inbox import create_inbox_item

        if _pending_retry_diagnosis(run_meta, human_turn, signature):
            return
        create_inbox_item(
            folder,
            kind="retry_diagnosis",
            source="retry_guard",
            prompt=f"동일 원인으로 재시도가 반복되었습니다: {diagnosis}",
            summary=diagnosis,
            options=[
                {"id": "approve", "label": "강제로 재시도"},
                {"id": "reject", "label": "취소"},
            ],
            refs=[str(human_turn), signature, *agents],
        )
    except Exception:  # fail-open: escalation must never block the retry-blocked response
        import logging

        logging.getLogger(__name__).warning("retry diagnosis escalation failed for %s", folder, exc_info=True)


def _consume_force_ack(run_meta: RunStateLike, human_turn: int, signature: str) -> bool:
    ack = run_meta.get("retry_force_ack")
    if not isinstance(ack, dict):
        return False
    return ack.get("turn") == human_turn and ack.get("signature") == signature


def retry_failed_agents(
    folder: Path,
    *,
    agents: list[str] | None = None,
    on_event: Any = None,
    permissions: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Re-invoke the last turn's failed agents, preserving successful replies.

    Returns a summary {status, retried, succeeded, failed_agents, human_turn}.
    Raises RetryError(code=409|422) when the last turn is not partial or is a
    consensus/verified turn, or (C1) when this is a same-signature repeat of
    the immediately preceding retry — see module docstring. ``force=True``
    (or a prior Human Inbox "강제로 재시도" approval) bypasses that guard once.
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

    errors = _last_errors(turn)
    signature = _failure_signature(subset, errors)
    acknowledged = _consume_force_ack(run_meta, human_turn, signature)
    if not force and not acknowledged:
        history = list(run_meta.get("retry_history") or [])
        last_for_turn = next((h for h in reversed(history) if h.get("turn") == human_turn), None)
        if last_for_turn is not None and last_for_turn.get("signature") == signature:
            diagnosis = diagnosis_line(subset, errors)
            _escalate_retry_diagnosis(folder, run_meta, subset, human_turn, signature, diagnosis)
            raise RetryError(
                f"{diagnosis} — 이전 재시도와 동일한 실패라 자동 재시도를 막았습니다. "
                "Human Inbox에서 강제 재시도를 승인하세요.",
                code=409,
            )

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
        history.append(
            {
                "turn": human_turn,
                "agents": subset,
                "succeeded": now_succeeded,
                "ts": _now(),
                "signature": signature,
            }
        )
        run["retry_history"] = history
        if acknowledged:
            run.pop("retry_force_ack", None)  # one-time bypass consumed
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


def handle_retry_diagnosis_inbox_resolve(
    folder: Path,
    item: dict[str, Any],
    *,
    selected: list[str] | None,
    status: str,
) -> None:
    """Side-effect helper when inbox retry_diagnosis is resolved (mirrors skill_drafts).

    "강제로 재시도" only records a one-time acknowledgment — it does NOT invoke
    agents itself (Inbox resolve has no live SSE/on_event context to stream
    into). The next explicit retry click sees the ack and bypasses the guard
    once (``_consume_force_ack``).
    """
    if item.get("kind") != "retry_diagnosis":
        return
    if status in ("rejected", "superseded"):
        return
    choice = (selected or [""])[0].strip().lower()
    if choice != "approve":
        return
    refs = list(item.get("refs") or [])
    if len(refs) < 2:
        return
    turn, signature = refs[0], refs[1]
    try:
        human_turn = int(turn)
    except ValueError:
        return

    from agent_lab.run.meta import patch_run_meta

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        run["retry_force_ack"] = {"turn": human_turn, "signature": signature, "acknowledged_at": _now()}
        return run

    patch_run_meta(folder, _patch)
