"""Deterministic discuss harvest → Human Inbox question items (M3–M4).

Peer ``CHALLENGE``/``AMEND`` envelopes belong in ``room_objections`` — not Inbox.
Inbox questions are Human-direction only:

- ``DECISION-FORK`` blocks → ref-anchored option questions (M4) → ``T-Q1`` (pause-eligible)
- ``plan.md`` OPEN bullets → ``T-Q2`` (pause-eligible)
- Clarifier → ``T-Q0`` (pause-eligible)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha1
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.human_inbox import (
    append_inbox_item,
    has_pending_question,
    inbox_items,
    new_inbox_item,
)

_AGENT_IDS = frozenset({"cursor", "codex", "claude"})
_HARVEST_ACTS = frozenset({"CHALLENGE", "AMEND"})
_MAX_ITEMS = 3
_EXCERPT_CHARS = 240
_PROMPT_CHARS = 160


def orchestrator_inbox_harvest_enabled() -> bool:
    """Legacy post-turn Python harvest → Inbox (``source=orchestrator``).

    MCP-first default is **off**; peers use ``ask_human`` / ``propose_build`` MCP.
    Set ``AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST=1`` to restore supervisor harvest.
    """
    raw = os.getenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def orchestrator_inbox_harvest_allowed(run_meta: RunStateLike | None) -> bool:
    """True when orchestrator may run discuss/build harvest for this session.

    MCP-first: legacy question harvest is off by default. Plan-workflow CLARIFY no
    longer force-enables it — plan.md OPEN bullets and forks surface via the peer
    ``ask_human`` MCP path, not the orchestrator scrape. Build harvest stays gated
    on the explicit ``AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST`` opt-in.
    """
    from agent_lab.room.preset import is_fast_room_session

    if run_meta and is_fast_room_session(run_meta):
        return False
    return orchestrator_inbox_harvest_enabled()


def discuss_fork_harvest_allowed(run_meta: RunStateLike | None) -> bool:
    """Harvest ``decision-fork`` blocks from agent replies into Inbox (T-Q1).

    MCP-first still prefers ``ask_human`` from the gate owner, but R2+ reply_policy
    continues to inject ```decision-fork``` fences — bridge those into the Question
    widget without re-enabling full orchestrator harvest (plan OPEN / clarifier).
    """
    from agent_lab.room.preset import is_fast_room_session

    return not (run_meta and is_fast_room_session(run_meta))


@dataclass(frozen=True)
class InboxQuestionCandidate:
    """A deterministic harvest hit — prompt + refs/excerpt.

    ``options`` is empty for M3 sources (CHALLENGE/AMEND, plan OPEN). M4 FORK
    candidates carry ref-anchored options from the Facilitator.
    """

    prompt: str
    excerpt: str
    refs: tuple[str, ...]
    trigger: str
    harvest_key: str
    options: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "excerpt": self.excerpt,
            "refs": list(self.refs),
            "trigger": self.trigger,
            "harvest_key": self.harvest_key,
            "options": [dict(o) for o in self.options],
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
    from agent_lab.agent.envelope import parse_agent_response

    parsed = parse_agent_response(getattr(m, "content", "") or "")
    return parsed.envelope.to_dict() if parsed.envelope else None


def escalation_harvest_keys_from_batch(messages: list[Any], *, act: str) -> list[str]:
    """Harvest keys for act messages already consumed by topic-router escalation."""
    from agent_lab.agent.envelope import envelope_act

    act_u = str(act or "").upper()
    if act_u not in _HARVEST_ACTS:
        return []
    keys: list[str] = []
    for m in messages:
        if getattr(m, "role", None) != "agent":
            continue
        agent = str(getattr(m, "agent", "") or "").strip().lower()
        if agent not in _AGENT_IDS:
            continue
        env = _envelope_dict(m)
        if not env or envelope_act(env) != act_u:
            continue
        message = str(env.get("message") or getattr(m, "content", "") or "").strip()
        if not message:
            continue
        keys.append(_fingerprint(agent, act_u, message[:120]))
    return keys


def record_escalation_harvest_keys(
    run_meta: RunStateLike,
    batch_msgs: list[Any],
    *,
    act: str,
) -> None:
    """Skip inbox harvest for CHALLENGE/AMEND/BLOCK that bumped category this turn."""
    new_keys = escalation_harvest_keys_from_batch(batch_msgs, act=act)
    if not new_keys:
        return
    prev = run_meta.get("_escalation_harvest_keys")
    merged = {str(k) for k in (prev or []) if k} | set(new_keys)
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, _escalation_harvest_keys=sorted(merged))


def _challenge_amend_candidates(messages: list[Any]) -> list[InboxQuestionCandidate]:
    from agent_lab.agent.envelope import envelope_act

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
        refs = tuple(str(r).strip() for r in (env.get("refs") or []) if str(r).strip())
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
    from agent_lab.room.context import extract_open_bullets

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


def _fork_candidates(messages: list[Any]) -> list[InboxQuestionCandidate]:
    """M4: DECISION-FORK blocks → ref-anchored option questions (Facilitator)."""
    from agent_lab.agent.envelope import parse_decision_forks
    from agent_lab.inbox.facilitator import facilitate

    forks = []
    for m in _turn_messages(messages):
        if getattr(m, "role", None) != "agent":
            continue
        agent = str(getattr(m, "agent", "") or "").strip().lower()
        if agent not in _AGENT_IDS:
            continue
        forks.extend(parse_decision_forks(getattr(m, "content", "") or ""))

    out: list[InboxQuestionCandidate] = []
    for q in facilitate(forks):
        out.append(
            InboxQuestionCandidate(
                prompt=q.prompt[:_PROMPT_CHARS],
                excerpt="",
                refs=q.refs,
                trigger="T-Q1",
                harvest_key=q.harvest_key,
                options=q.options,
            )
        )
    return out


def harvest_question_candidates(
    messages: list[Any],
    *,
    plan_md: str = "",
    include_forks: bool = True,
    include_plan_open: bool = True,
) -> list[InboxQuestionCandidate]:
    """Pure deterministic harvest — no I/O, no LLM synthesis. Deduped + capped.

    FORK (ref-anchored options) and plan OPEN only — not envelope CHALLENGE/AMEND.
    """
    raw: list[InboxQuestionCandidate] = []
    if include_forks:
        raw.extend(_fork_candidates(messages))
    if include_plan_open:
        raw.extend(_plan_open_candidates(plan_md))
    seen: set[str] = set()
    out: list[InboxQuestionCandidate] = []
    for c in raw:
        if c.harvest_key in seen:
            continue
        seen.add(c.harvest_key)
        out.append(c)
    return out[:_MAX_ITEMS]


def _existing_harvest_keys(run: RunStateLike) -> set[str]:
    return {str(item.get("harvest_key")) for item in inbox_items(run) if item.get("harvest_key")}


def clarifier_harvest_key(question: str) -> str:
    return _fingerprint("clarifier", question[:120])


def harvest_clarifier_questions(
    run_meta: RunStateLike,
    questions: list[str],
    *,
    human_turn: int | None = None,
    question_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """M2b: clarifier gate → Inbox question items (T-Q0, multiple choice when available)."""
    if not orchestrator_inbox_harvest_allowed(run_meta):
        return []
    if not questions:
        return []
    from agent_lab.plan.clarify_options import options_for_clarifier_question

    rows_by_prompt: dict[str, dict[str, Any]] = {}
    for row in question_rows or []:
        if isinstance(row, dict):
            prompt = str(row.get("prompt") or "").strip()
            if prompt:
                rows_by_prompt[prompt] = row
    existing = _existing_harvest_keys(run_meta)
    created: list[dict[str, Any]] = []
    for q in questions:
        text = (q or "").strip()
        if not text:
            continue
        key = clarifier_harvest_key(text)
        if key in existing:
            continue
        row = rows_by_prompt.get(text) or {"prompt": text}
        options = options_for_clarifier_question(row)
        item = new_inbox_item(
            kind="question",
            source="orchestrator",
            prompt=text,
            options=options,
            trigger="T-Q0",
            harvest_key=key,
            human_turn_id=human_turn,
        )
        append_inbox_item(run_meta, item)
        existing.add(key)
        created.append(item)
    return created


def _current_plan_revision(run_meta: RunStateLike, plan_md: str) -> str:
    lpu = run_meta.get("last_plan_update") or {}
    ts = lpu.get("completed_at") or lpu.get("ts")
    if ts:
        return str(ts)
    excerpt = (plan_md or "").strip()[:500]
    return "plan-" + sha1(excerpt.encode("utf-8")).hexdigest()[:12]


def harvest_discuss_questions(
    run_meta: RunStateLike,
    messages: list[Any],
    *,
    human_turn: int | None = None,
    plan_md: str = "",
    mode: str = "discuss",
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Surface deterministic discuss questions into the in-memory ``run_meta`` (M3).

    - ``options=[]`` always; ``source="orchestrator"`` (M4 adds FORK options).
    - Idempotent: a candidate whose ``harvest_key`` already exists in the inbox
      (any status) is skipped, so a fork is surfaced once, not re-nagged each turn.
    - Caller persists ``run_meta``.

    Returns the items created this call.
    """
    fork_ok = discuss_fork_harvest_allowed(run_meta)
    orch_ok = orchestrator_inbox_harvest_allowed(run_meta)
    if not fork_ok and not orch_ok:
        return []
    if mode != "discuss":
        return []
    candidates = harvest_question_candidates(
        messages,
        plan_md=plan_md,
        include_forks=fork_ok,
        include_plan_open=orch_ok,
    )
    if not candidates:
        return []
    skip_escalation = {str(k) for k in (run_meta.get("_escalation_harvest_keys") or []) if k}
    existing = _existing_harvest_keys(run_meta)
    created: list[dict[str, Any]] = []
    for c in candidates:
        if c.harvest_key in skip_escalation:
            continue
        if c.harvest_key in existing:
            continue
        item = new_inbox_item(
            kind="question",
            source="orchestrator",
            prompt=c.prompt,
            options=[dict(o) for o in c.options],
            summary=c.excerpt or None,
            context_ref=(c.refs[0] if c.refs else None),
            trigger=c.trigger,
            refs=list(c.refs),
            harvest_key=c.harvest_key,
            human_turn_id=human_turn,
        )
        append_inbox_item(run_meta, item)
        existing.add(c.harvest_key)
        created.append(item)
        if session_id:
            from agent_lab.human_inbox import fan_out_inbox_item

            fan_out_inbox_item(session_id, item)
    return created


# --- Build proposal harvest (M5) — T-B gates → execute GO 예고 -----------------

_PENDING_EXEC_STATUS = "pending_approval"  # mirrors plan_execute.PENDING_STATUS


def _has_pending_execution(run: RunStateLike) -> bool:
    for row in run.get("executions") or []:
        if isinstance(row, dict) and row.get("status") == _PENDING_EXEC_STATUS:
            return True
    return False


def _build_summary(action: dict[str, Any]) -> str:
    what = str(action.get("what") or "").strip() or "실행 대기 action"
    bits: list[str] = []
    where = str(action.get("where") or "").strip()
    verify = str(action.get("verify") or "").strip()
    if where:
        bits.append(f"위치: {where}")
    if verify:
        bits.append(f"검증: {verify}")
    summary = what if not bits else f"{what} — " + " · ".join(bits)
    return summary[:300]


def harvest_build_proposal(
    run_meta: RunStateLike,
    *,
    plan_md: str = "",
    human_turn: int | None = None,
    mode: str = "discuss",
) -> dict[str, Any] | None:
    """T-B gates → one Inbox build item ("실행할까?"). In-memory; caller persists.

    Gates (RFC §5.4 / §3.2):
    - ordering: no pending question (question precedes build)
    - **T-B1**: a recommended executable ``## 지금 실행`` action exists
    - **T-B2**: no open BLOCK objection on that action
    - **T-B3**: no pending execution + no existing build item for the action (dedupe)

    The dry-run endpoint re-checks the full gates (objection, pre_execute,
    snapshot), so this surfaces optimistically; GO is the authoritative gate.
    """
    if not orchestrator_inbox_harvest_allowed(run_meta):
        return None
    if mode != "discuss":
        return None
    if has_pending_question(run_meta):  # §3.2 ordering — question precedes build
        return None

    from agent_lab.plan.actions import parse_plan_action_sections

    recommended = parse_plan_action_sections(plan_md).get("recommended")
    if not recommended:  # T-B1
        return None

    action_index = int(recommended.get("index") or 0)
    action_kind_raw = str(recommended.get("kind") or "now")
    action_ref = str(recommended.get("action_key") or f"{action_kind_raw}:{action_index}")

    from agent_lab.plan.actions import PlanActionKind, parse_action_key
    from agent_lab.room.objections import execute_block_reason_for_action

    parsed_kind = parse_action_key(f"{action_kind_raw}:{action_index}")
    action_kind: PlanActionKind = parsed_kind[0] if parsed_kind else "now"
    if execute_block_reason_for_action(run_meta, action_index, action_kind):  # T-B2
        return None
    if _has_pending_execution(run_meta):  # T-B3
        return None

    harvest_key = f"build-{action_ref}"
    if harvest_key in _existing_harvest_keys(run_meta):  # T-B3 dedupe
        return None

    summary = _build_summary(recommended)
    item = new_inbox_item(
        kind="build",
        source="orchestrator",
        prompt=summary,
        summary=summary,
        action_ref=action_ref,
        trigger="T-B1",
        harvest_key=harvest_key,
        human_turn_id=human_turn,
        plan_revision=_current_plan_revision(run_meta, plan_md),
    )
    append_inbox_item(run_meta, item)
    return item


def harvest_post_plan_inbox(
    run_meta: RunStateLike,
    messages: list[Any],
    *,
    plan_md: str,
    human_turn: int | None = None,
) -> dict[str, Any]:
    """After plan scribe (consensus or verified): T-Q2 OPEN + T-B1 build."""
    harvest_discuss_questions(
        run_meta,
        messages,
        human_turn=human_turn,
        plan_md=plan_md,
        mode="discuss",
    )
    build_item = harvest_build_proposal(
        run_meta,
        plan_md=plan_md,
        human_turn=human_turn,
        mode="discuss",
    )
    return {
        "questions": sum(1 for i in inbox_items(run_meta) if i.get("kind") == "question"),
        "build_created": build_item is not None,
    }


def _supersede_legacy_verified_build_items(run_meta: RunStateLike) -> None:
    """Drop direct verified-loop build shortcuts superseded by plan pipeline."""
    items = inbox_items(run_meta)
    changed = False
    for item in items:
        if item.get("kind") == "build" and item.get("source") == "verified_loop" and item.get("status") == "pending":
            item["status"] = "superseded"
            item["resolved_at"] = _now_iso_verified_supersede()
            changed = True
    if changed:
        from agent_lab.human_inbox import compute_inbox_pending
        from agent_lab.run.meta import stamp_run_meta

        stamp_run_meta(run_meta, human_inbox=items)
        stamp_run_meta(run_meta, inbox_pending=compute_inbox_pending(run_meta))


def _now_iso_verified_supersede() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# --- sync pause (M4) — pending Human-direction question pauses debate rounds ----

DISCUSS_PAUSE_TRIGGERS = frozenset({"T-Q0", "T-Q2"})
_HUMAN_QUESTION_SOURCES = frozenset(
    {"manual", "mission_circuit_break", "mcp_ask_human", "gateway"}
)


def inbox_question_pauses_discuss(item: dict[str, Any]) -> bool:
    """True when a pending inbox question should halt auto discuss rounds."""
    if item.get("kind") != "question" or item.get("status") != "pending":
        return False
    trigger = str(item.get("trigger") or "").strip()
    if trigger in DISCUSS_PAUSE_TRIGGERS:
        return True
    if trigger == "T-Q1":
        options = item.get("options")
        return isinstance(options, list) and len(options) >= 2
    source = str(item.get("source") or "").strip().lower()
    return source in _HUMAN_QUESTION_SOURCES


def has_pending_discuss_pause_question(run_meta: RunStateLike) -> bool:
    return any(inbox_question_pauses_discuss(item) for item in inbox_items(run_meta))


def inbox_mode() -> str:
    """``AGENT_LAB_INBOX_MODE`` — ``sync`` (default) pauses discuss; ``soft`` surfaces only."""
    mode = os.getenv("AGENT_LAB_INBOX_MODE", "sync").strip().lower()
    return mode if mode in ("sync", "soft") else "sync"


def inbox_mode_for_run(run_meta: RunStateLike | None) -> str:
    """Session ``inbox_mode`` overrides env when set to sync|soft."""
    if isinstance(run_meta, dict):
        raw = str(run_meta.get("inbox_mode") or "").strip().lower()
        if raw in ("sync", "soft"):
            return raw
    return inbox_mode()


def should_pause_discuss(run_meta: RunStateLike) -> bool:
    """Sync checkpoint: pause-eligible pending question halts further auto rounds."""
    import os

    if inbox_mode_for_run(run_meta) != "sync":
        return False
    if not has_pending_discuss_pause_question(run_meta):
        return False
    if os.getenv("AGENT_LAB_GATE_SCOPE", "1").strip().lower() not in ("0", "false", "no"):
        from agent_lab.gate_scope import should_pause_discuss_for_profile

        return should_pause_discuss_for_profile(run_meta)
    return True


INBOX_FORK_GRACE_GUIDANCE = (
    "[Inbox fork grace round]\n"
    "Human Inbox에 방향 fork가 올라갔습니다. 동료 옵션에 ENDORSE/AMEND/PASS로 짧게 반응하세요. "
    "새 `decision-fork` 블록은 금지 — Human 선택을 기다립니다."
)

INBOX_TQ2_GRACE_GUIDANCE = (
    "[Inbox plan-open grace round]\n"
    "plan.md OPEN 항목이 Human Inbox에 올라갔습니다. 동료들이 ENDORSE/AMEND/PASS로 짧게 반응하세요. "
    "새 OPEN bullet 추가는 금지 — Human 결정을 기다립니다."
)

PAUSE_GRACE_KIND_FORK = "fork"
PAUSE_GRACE_KIND_PLAN_OPEN = "plan_open"


def clear_inbox_pause_grace(run_meta: RunStateLike | None) -> None:
    if isinstance(run_meta, dict):
        run_meta.pop("_inbox_pause_grace_pending", None)
        run_meta.pop("_inbox_pause_grace_kind", None)
        run_meta.pop("_inbox_fork_grace_pending", None)


clear_inbox_fork_grace = clear_inbox_pause_grace


def inbox_pause_grace_pending(run_meta: RunStateLike | None) -> bool:
    if not isinstance(run_meta, dict):
        return False
    return bool(run_meta.get("_inbox_pause_grace_pending") or run_meta.get("_inbox_fork_grace_pending"))


inbox_fork_grace_pending = inbox_pause_grace_pending


def inbox_pause_grace_kind(run_meta: RunStateLike | None) -> str | None:
    if not isinstance(run_meta, dict):
        return None
    kind = str(run_meta.get("_inbox_pause_grace_kind") or "").strip()
    if kind in (PAUSE_GRACE_KIND_FORK, PAUSE_GRACE_KIND_PLAN_OPEN):
        return kind
    if run_meta.get("_inbox_fork_grace_pending") or run_meta.get("_inbox_pause_grace_pending"):
        return PAUSE_GRACE_KIND_FORK
    return None


def inbox_pause_grace_guidance(run_meta: RunStateLike | None) -> str:
    if inbox_pause_grace_kind(run_meta) == PAUSE_GRACE_KIND_PLAN_OPEN:
        return INBOX_TQ2_GRACE_GUIDANCE
    return INBOX_FORK_GRACE_GUIDANCE


def _item_qualifies_for_pause_grace(item: dict[str, Any]) -> bool:
    if not inbox_question_pauses_discuss(item):
        return False
    trigger = str(item.get("trigger") or "").strip()
    if trigger == "T-Q1":
        options = item.get("options")
        return isinstance(options, list) and len(options) >= 2
    return trigger == "T-Q2"


def _pause_grace_kind_for_item(item: dict[str, Any]) -> str:
    trigger = str(item.get("trigger") or "").strip()
    if trigger == "T-Q2":
        return PAUSE_GRACE_KIND_PLAN_OPEN
    return PAUSE_GRACE_KIND_FORK


def harvest_and_check_pause(
    run_meta: RunStateLike,
    messages: list[Any],
    *,
    human_turn: int | None = None,
    plan_md: str = "",
    mode: str = "discuss",
    session_id: str | None = None,
) -> bool:
    """Harvest this round's questions into ``run_meta`` then report sync-pause.

    FORK (T-Q1 + options) and T-Q2 (plan OPEN) each get one grace debate round
    for peer ENDORSE/AMEND before ``should_pause_discuss`` stops further auto rounds.
    """
    if not discuss_fork_harvest_allowed(run_meta) and not orchestrator_inbox_harvest_allowed(run_meta):
        return False
    had_pause = has_pending_discuss_pause_question(run_meta)
    created = harvest_discuss_questions(
        run_meta,
        messages,
        human_turn=human_turn,
        plan_md=plan_md,
        mode=mode,
        session_id=session_id,
    )
    if not should_pause_discuss(run_meta):
        clear_inbox_pause_grace(run_meta)
        return False

    new_grace = [item for item in created if _item_qualifies_for_pause_grace(item)]
    if new_grace and not had_pause:
        if not inbox_pause_grace_pending(run_meta):
            from agent_lab.run.meta import stamp_run_meta

            stamp_run_meta(
                run_meta,
                _inbox_pause_grace_pending=True,
                _inbox_pause_grace_kind=_pause_grace_kind_for_item(new_grace[0]),
            )
            return False
    clear_inbox_pause_grace(run_meta)
    return True
