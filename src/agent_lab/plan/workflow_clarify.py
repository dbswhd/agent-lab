from __future__ import annotations

"""Plan workflow CLARIFY — clarity gate and agent blocks."""
from pathlib import Path
from typing import Any

from agent_lab.plan.workflow_state import (
    _mirror_verified_loop_status,
    get_plan_workflow,
    plan_workflow_wants_inbox_mcp,
    plan_fsm_skill_first_enabled,
)
from agent_lab.time_utils import utc_now_iso as _now
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.run.state import RunStateLike


def build_clarify_context_block(folder: Path) -> str:
    from agent_lab.human_inbox import inbox_items

    run = read_run_meta(folder)
    rows: list[str] = []
    for item in inbox_items(run):
        if item.get("kind") != "question":
            continue
        if item.get("status") not in {"resolved", "deferred"}:
            continue
        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            continue
        choice = item.get("resolved_choice")
        selected = item.get("resolved_selected")
        answer = choice if choice is not None else selected
        if answer is None:
            answer = item.get("resolved_note") or item.get("resolved_text") or ""
        rows.append(f"Q: {prompt}\nA: {answer}")
    if not rows:
        return ""
    return "## Clarifier answers (Human Inbox)\n\n" + "\n\n".join(rows)


def clarifier_topic(run: RunStateLike) -> str:
    from agent_lab.clarity import _mission_clarity_text

    return _mission_clarity_text(run)


def pending_clarifier_questions(interview: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not interview or interview.get("status") == "complete":
        return []
    answers_raw = interview.get("answers")
    answers: dict[str, Any] = answers_raw if isinstance(answers_raw, dict) else {}
    pending: list[dict[str, Any]] = []
    for q in interview.get("questions") or []:
        if not isinstance(q, dict):
            continue
        prompt = str(q.get("prompt") or "").strip()
        if not prompt:
            continue
        qid = str(q.get("id") or "")
        if str(answers.get(qid, "") or "").strip():
            continue
        pending.append(q)
    return pending


def inbox_question_surfaces_prompt(run: RunStateLike, prompt: str) -> bool:
    from agent_lab.human_inbox import inbox_items

    text = prompt.strip()
    if not text:
        return False
    for item in inbox_items(run):
        if item.get("kind") != "question":
            continue
        if str(item.get("prompt") or "").strip() != text:
            continue
        if item.get("status") in {"pending", "resolved"}:
            return True
    return False


def ensure_plan_clarify_interview(folder: Path) -> dict[str, Any] | None:
    """Ensure clarity-engine interview exists before the room turn (MCP-first CLARIFY)."""
    run = read_run_meta(folder)
    if not plan_workflow_wants_inbox_mcp(run):
        return None
    from agent_lab.session.clarifier import get_clarifier_interview

    existing = get_clarifier_interview(run)
    if isinstance(existing, dict) and existing.get("status") != "complete":
        return existing
    if plan_fsm_skill_first_enabled():
        return None
    from agent_lab.clarity import clarity_threshold_met

    if clarity_threshold_met(run):
        return None
    hold = clarity_gate_questions(folder, run)
    return get_clarifier_interview(read_run_meta(folder)) if hold else None


def ensure_plan_clarify_inbox_question(folder: Path) -> dict[str, Any] | None:
    """Surface the next pending clarifier question in Human Inbox with choice options (one at a time)."""
    run = read_run_meta(folder)
    if not plan_workflow_wants_inbox_mcp(run):
        return None
    from agent_lab.human_inbox import create_inbox_item, has_pending_question, inbox_items
    from agent_lab.inbox.harvest import clarifier_harvest_key
    from agent_lab.plan.clarify_options import options_for_clarifier_question
    from agent_lab.session.clarifier import get_clarifier_interview

    interview = get_clarifier_interview(run)
    pending = pending_clarifier_questions(interview)
    if not pending:
        return None
    prompt = str(pending[0].get("prompt") or "").strip()
    if has_pending_question(run):
        for item in inbox_items(run):
            if item.get("kind") == "question" and item.get("status") == "pending":
                if str(item.get("prompt") or "").strip() == prompt:
                    return item
        return None
    if inbox_question_surfaces_prompt(run, prompt):
        for item in inbox_items(run):
            if item.get("kind") == "question" and str(item.get("prompt") or "").strip() == prompt:
                return item
        return None
    topic = clarifier_topic(run)
    question = pending[0]
    options = options_for_clarifier_question(question, topic=topic)
    return create_inbox_item(
        folder,
        kind="question",
        source="orchestrator",
        prompt=prompt,
        options=options,
        trigger="T-Q0",
        harvest_key=clarifier_harvest_key(prompt),
    )


def build_plan_clarify_agent_block(folder: Path, *, agent_id: str, run_meta: RunStateLike | None) -> str:
    """Gate-owner instructions: ask_human with options, or wait on existing Inbox row."""
    if not run_meta or not plan_workflow_wants_inbox_mcp(run_meta):
        return ""
    from agent_lab.human_inbox import has_pending_question, inbox_items
    from agent_lab.inbox.mcp_policy import inbox_gate_owner
    from agent_lab.plan.clarify_options import options_for_clarifier_question
    from agent_lab.session.clarifier import get_clarifier_interview

    owner = inbox_gate_owner(run_meta)
    if str(agent_id or "").strip().lower() != owner:
        return (
            "Plan CLARIFY: only the inbox gate owner posts `ask_human`. Continue peer analysis; do not call ask_human."
        )
    run = read_run_meta(folder)
    if has_pending_question(run):
        pending = next(
            (i for i in inbox_items(run) if i.get("kind") == "question" and i.get("status") == "pending"),
            None,
        )
        if pending:
            opts = pending.get("options") or []
            opt_lines = ", ".join(
                f"{o.get('id')}:{o.get('label')}" for o in opts if isinstance(o, dict) and o.get("label")
            )
            return (
                "## Plan CLARIFY — Human Inbox pending\n"
                f"Q: {pending.get('prompt') or ''}\n"
                f"Options already shown: {opt_lines or '(see Inbox)'}\n"
                "Do NOT call ask_human again for this question. Wait for Human to answer in Inbox."
            )
    interview = get_clarifier_interview(run)
    pending_q = pending_clarifier_questions(interview)
    if not pending_q:
        return ""
    topic = clarifier_topic(run)
    q = pending_q[0]
    prompt = str(q.get("prompt") or "").strip()
    options = options_for_clarifier_question(q, topic=topic)
    import json

    options_json = json.dumps(options, ensure_ascii=False)
    return (
        "## Plan CLARIFY — post ONE ask_human (multiple choice)\n"
        f"Question: {prompt}\n"
        f"Suggested options (adapt labels to the topic): {options_json}\n"
        "Call ask_human with this question and >=2 contextual options NOW. "
        "One question only; Human answers in Inbox before the next."
    )


PLAN_CLARIFY_GUIDANCE = (
    "Plan workflow CLARIFY: Human gate is ONLY via `ask_human` MCP (never prose questions). "
    "One question per call; each call needs >=2 options with id+label (+ optional description). "
    "Derive options from the topic — use the pending-question block when present. "
    "Example: ask_human(question='완료 기준은?', options="
    '[{"id":"pytest","label":"pytest"},{"id":"make_ci","label":"make ci"}]). '
    "After Human answers in Inbox, continue peer work — do not re-ask the same question."
)


def open_plan_objections(run: RunStateLike) -> list[dict[str, Any]]:
    from agent_lab.room.objections import list_objections

    return [o for o in list_objections(run) if o.get("status") == "open" and o.get("act") in {"CHALLENGE", "BLOCK"}]


def clarity_gate_questions(folder: Path, run: RunStateLike) -> dict[str, Any] | None:
    """Engine+pipeline CLARIFY gate: surface clarity-engine questions via the Human Inbox.

    Returns a hold-result dict when CLARIFY must hold on unmet clarity, or ``None`` when clarity
    is already met or no human-visible question could be created (no silent deadlock). Anchored
    tasks (regex short-circuit) pass immediately without an LLM call.
    """
    from agent_lab.clarity import _mission_clarity_text, clarity_threshold_met

    if clarity_threshold_met(run):
        return None

    from agent_lab.clarifier_engine import engine_questions

    text = _mission_clarity_text(run)
    _result, questions = engine_questions(text)
    if not questions:
        # Clarity unmet but no targeted question to ask → do not silently hold; advance.
        return {"phase": "CLARIFY", "clarity_pending": False, "clarity_notice": "clarity_no_questions"}

    from agent_lab.inbox.harvest import harvest_clarifier_questions
    from agent_lab.plan.clarify_options import attach_options_to_questions
    from agent_lab.session.clarifier import persist_clarifier_interview

    topic = _mission_clarity_text(run)
    questions = attach_options_to_questions(questions[:5], topic=topic)
    interview = {
        "version": 2,
        "plan_mode": True,
        "status": "pending",
        "source": "clarity_engine",
        "human_turn": 0,
        "questions": questions[:5],
        "answers": {},
        "created_at": _now(),
    }
    # Persist through the identity-aware arbiter and harvest from the ACTUAL persisted
    # interview (which may be a preserved pre-existing pending one), so the Human Inbox can
    # never diverge from run.json's clarifier_interview.
    persisted = persist_clarifier_interview(folder, interview)
    actual: dict[str, Any] = persisted.get("interview") or interview
    prompts = [
        str(q.get("prompt") or "").strip()
        for q in (actual.get("questions") or [])
        if str(q.get("prompt") or "").strip()
    ]
    if not prompts:
        return {"phase": "CLARIFY", "clarity_pending": False, "clarity_notice": "clarity_no_questions"}

    def _harvest(run_in: dict[str, Any]) -> dict[str, Any]:
        rows = [q for q in (actual.get("questions") or []) if isinstance(q, dict)]
        harvest_clarifier_questions(run_in, prompts, question_rows=rows)
        cur = get_plan_workflow(run_in)
        cur["phase"] = "CLARIFY"
        cur["notice"] = "clarity_pending"
        run_in["plan_workflow"] = cur
        _mirror_verified_loop_status(run_in, cur)
        return run_in

    patch_run_meta(folder, _harvest)

    from agent_lab.human_inbox import has_pending_question

    if not has_pending_question(read_run_meta(folder)):
        from agent_lab.inbox.harvest import orchestrator_inbox_harvest_enabled

        if orchestrator_inbox_harvest_enabled():
            # Harvest was enabled but questions were all deduped → advance to avoid deadlock.
            return {"phase": "CLARIFY", "clarity_pending": False, "clarity_notice": "clarity_no_visible_question"}
        # MCP-first: seed Human Inbox with the next multiple-choice clarifier question.
        ensure_plan_clarify_inbox_question(folder)
        return {
            "phase": "CLARIFY",
            "clarity_pending": True,
            "clarity_notice": "clarity_mcp_first_hold",
            "questions": prompts,
            "wait_inbox": False,
        }
    return {
        "phase": "CLARIFY",
        "clarity_pending": True,
        "clarity_notice": "clarity_pending",
        "questions": prompts,
        "wait_inbox": True,
    }
