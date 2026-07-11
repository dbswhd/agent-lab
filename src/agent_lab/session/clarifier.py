"""Clarifier gate + plan-mode structured interview v2 (MB-7)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from agent_lab.time_utils import utc_now_iso as _now_iso
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.run.state import RunStateLike

ClarifierCategory = Literal["goal", "scope", "verify", "constraints", "priority", "criteria", "context"]


def clarifier_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_CLARIFIER") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def interview_v2_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_CLARIFIER_INTERVIEW") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return clarifier_enabled()


def clarifier_min_topic_chars() -> int:
    try:
        return max(8, int(os.getenv("AGENT_LAB_CLARIFIER_MIN_CHARS", "48")))
    except ValueError:
        return 48


def _question(
    qid: str,
    category: ClarifierCategory,
    prompt: str,
) -> dict[str, str]:
    return {"id": qid, "category": category, "prompt": prompt}


def _plan_interview_questions(*, short: bool, first_turn: bool) -> list[dict[str, str]]:
    core = [
        _question(
            "goal",
            "goal",
            "plan.md로 달성할 결과물과 Human이 기대하는 완료 상태를 한 줄로 적어 주세요.",
        ),
        _question(
            "scope",
            "scope",
            "이번 계획에 포함할 경로/모듈과 의도적으로 제외할 영역을 적어 주세요.",
        ),
        _question(
            "verify",
            "verify",
            "plan action의 검증 기준(테스트·산출물·명령)을 구체적으로 적어 주세요.",
        ),
    ]
    if short or first_turn:
        core.append(
            _question(
                "constraints",
                "constraints",
                "지켜야 할 제약(의존성, 금지 변경, 시간)이 있나요?",
            )
        )
    if short:
        core.append(
            _question(
                "priority",
                "priority",
                "첫 execute action에서 가장 먼저 다룰 항목은 무엇인가요?",
            )
        )
    return core[:5]


def _discuss_interview_questions(*, short: bool, first_turn: bool) -> list[dict[str, str]]:
    if short:
        return [
            _question(
                "goal",
                "goal",
                "이번 세션에서 가장 먼저 달성하려는 결과물은 무엇인가요? (파일·검증 기준 포함)",
            ),
            _question(
                "scope",
                "scope",
                "작업 범위(레포/경로)와 제외할 영역이 있나요?",
            ),
            _question(
                "verify",
                "verify",
                "완료를 어떤 검증으로 확인할까요?",
            ),
        ]
    if first_turn:
        return [
            _question(
                "goal",
                "goal",
                "Human이 기대하는 완료 기준(검증·산출물)을 한 줄로 적어 주세요.",
            ),
            _question(
                "scope",
                "scope",
                "작업 범위와 제외할 영역을 적어 주세요.",
            ),
        ]
    return []


def _legacy_plan_prompts(*, short: bool, first_turn: bool) -> list[str] | None:
    if first_turn:
        return _plan_short_questions() if short else _plan_first_turn_questions()
    if short:
        return _plan_short_questions()
    return None


def _legacy_discuss_prompts(*, short: bool, first_turn: bool) -> list[str] | None:
    if not short and not first_turn:
        return None
    if short:
        return _discuss_short_questions()
    return _discuss_first_turn_questions()


def _plan_short_questions() -> list[str]:
    return [
        "plan.md에 담을 성공 기준(검증·완료 조건)은 무엇인가요?",
        "이번 계획의 범위와 의도적으로 제외할 영역을 적어 주세요.",
    ]


def _plan_first_turn_questions() -> list[str]:
    return [
        "plan.md 완료를 어떤 검증(테스트·산출물)으로 확인할까요?",
        "계획 범위(레포/경로)와 제외할 작업이 있나요?",
    ]


def _discuss_short_questions() -> list[str]:
    return [
        "이번 세션에서 가장 먼저 달성하려는 결과물은 무엇인가요? (파일·검증 기준 포함)",
        "작업 범위(레포/경로)와 제외할 영역이 있나요?",
    ]


def _discuss_first_turn_questions() -> list[str]:
    return [
        "Human이 기대하는 완료 기준(검증·산출물)을 한 줄로 적어 주세요.",
    ]


def build_clarifier_interview(
    topic: str,
    *,
    is_new_session: bool,
    human_message_count: int = 0,
    plan_mode: bool = False,
) -> dict[str, Any] | None:
    """Structured 2–5 question interview (plan mode default when interview v2 on)."""
    if not clarifier_enabled():
        return None
    text = (topic or "").strip()
    if not text:
        return None
    from agent_lab.clarifier_engine import build_engine_interview

    engine_interview = build_engine_interview(
        text,
        human_message_count=human_message_count,
        plan_mode=plan_mode,
    )
    if engine_interview is not None:
        return engine_interview
    short = len(text) < clarifier_min_topic_chars()
    first_turn = is_new_session and human_message_count <= 1
    use_v2 = interview_v2_enabled()

    if plan_mode and use_v2:
        if not short and not first_turn:
            return None
        questions = _plan_interview_questions(short=short, first_turn=first_turn)
    elif plan_mode:
        legacy = _legacy_plan_prompts(short=short, first_turn=first_turn)
        if not legacy:
            return None
        questions = [_question(f"q{i + 1}", "goal", q) for i, q in enumerate(legacy)]
    elif use_v2:
        questions = _discuss_interview_questions(short=short, first_turn=first_turn)
        if not questions:
            return None
    else:
        legacy = _legacy_discuss_prompts(short=short, first_turn=first_turn)
        if not legacy:
            return None
        questions = [_question(f"q{i + 1}", "goal", q) for i, q in enumerate(legacy)]

    if len(questions) < 1:
        return None
    from agent_lab.plan.clarify_options import attach_options_to_questions

    questions = attach_options_to_questions(questions[:5], topic=text)
    return {
        "version": 2,
        "plan_mode": plan_mode,
        "status": "pending",
        "human_turn": human_message_count,
        "questions": questions[:5],
        "answers": {},
        "created_at": _now_iso(),
    }


def interview_prompts(interview: dict[str, Any] | None) -> list[str] | None:
    if not interview:
        return None
    questions = interview.get("questions")
    if not isinstance(questions, list):
        return None
    prompts = [
        str(q.get("prompt") or "").strip()
        for q in questions
        if isinstance(q, dict) and str(q.get("prompt") or "").strip()
    ]
    return prompts or None


def build_clarifier_questions(
    topic: str,
    *,
    is_new_session: bool,
    human_message_count: int = 0,
    plan_mode: bool = False,
) -> list[str] | None:
    """Return prompt lines for UI / inbox (backward compatible)."""
    if not clarifier_enabled():
        return None
    interview = build_clarifier_interview(
        topic,
        is_new_session=is_new_session,
        human_message_count=human_message_count,
        plan_mode=plan_mode,
    )
    prompts = interview_prompts(interview)
    if prompts:
        return prompts
    return None


def _interview_source(interview: dict[str, Any] | None) -> str:
    """Source tag of an interview; static server-clarifier interviews are unmarked → 'server'."""
    src = (interview or {}).get("source")
    return str(src) if src else "server"


def _question_ids(interview: dict[str, Any] | None) -> set[str]:
    questions = (interview or {}).get("questions") if isinstance(interview, dict) else None
    if not isinstance(questions, list):
        return set()
    return {str(q.get("id")) for q in questions if isinstance(q, dict) and q.get("id")}


def _persist_decision(
    existing: dict[str, Any] | None,
    candidate: dict[str, Any],
    *,
    replace: bool,
) -> tuple[bool, str]:
    """Decide whether ``candidate`` may replace ``existing`` as the durable interview.

    Identity-aware: a pending interview from a different source is preserved (write-race fix);
    a same-source write is allowed only when its question id set is a superset of the existing
    one so in-flight pending questions are never silently dropped.
    """
    if not isinstance(existing, dict):
        return True, "new"
    if replace:
        return True, "explicit_replace"
    if existing.get("status") == "complete":
        return True, "prior_complete"
    if _interview_source(existing) == _interview_source(candidate):
        if _question_ids(existing) <= _question_ids(candidate):
            return True, "same_source_update"
        return False, "same_source_divergent"
    return False, "cross_source_pending"


def persist_clarifier_interview(
    folder: Path,
    interview: dict[str, Any],
    *,
    replace: bool = False,
) -> dict[str, Any]:
    """Persist ``interview`` to run.json with identity-aware replacement semantics.

    Returns ``{"interview", "persisted", "reason"}`` where ``interview`` is the ACTUAL
    persisted state — the candidate when written, or the preserved existing interview when a
    cross-source pending replacement is blocked. Callers (room SSE) must render from the
    returned ``interview``, never from the candidate they passed in.
    """

    path = folder
    outcome: dict[str, Any] = {"interview": interview, "persisted": True, "reason": "new"}

    def _persist(run: dict[str, Any]) -> dict[str, Any]:
        existing = get_clarifier_interview(run)
        persisted, reason = _persist_decision(existing, interview, replace=replace)
        outcome["persisted"] = persisted
        outcome["reason"] = reason
        if persisted:
            run["clarifier_interview"] = interview
            outcome["interview"] = interview
        else:
            outcome["interview"] = existing
        return run

    patch_run_meta(path, _persist)
    return outcome


def get_clarifier_interview(run: RunStateLike | None) -> dict[str, Any] | None:
    raw = (run or {}).get("clarifier_interview")
    return raw if isinstance(raw, dict) else None


def public_clarifier_interview(run: RunStateLike | None) -> dict[str, Any] | None:
    interview = get_clarifier_interview(run)
    if not interview:
        return None
    raw_questions = interview.get("questions")
    questions: list[Any] = raw_questions if isinstance(raw_questions, list) else []
    raw_answers = interview.get("answers")
    answers: dict[str, Any] = raw_answers if isinstance(raw_answers, dict) else {}
    pending = [q for q in questions if isinstance(q, dict) and not str(answers.get(str(q.get("id") or ""), "")).strip()]
    return {
        "version": interview.get("version"),
        "plan_mode": interview.get("plan_mode"),
        "status": interview.get("status"),
        "human_turn": interview.get("human_turn"),
        "questions": questions,
        "answers": answers,
        "pending_count": len(pending),
        "created_at": interview.get("created_at"),
        "completed_at": interview.get("completed_at"),
    }


def record_clarifier_answers(
    folder: Path,
    *,
    answers: dict[str, str],
    mark_complete: bool = True,
) -> dict[str, Any] | None:
    path = folder

    def _record(run: dict[str, Any]) -> dict[str, Any]:
        interview = get_clarifier_interview(run)
        if not interview:
            return run
        merged = dict(interview.get("answers") or {})
        for key, value in answers.items():
            text = str(value or "").strip()
            if text:
                merged[str(key)] = text
        interview = dict(interview)
        interview["answers"] = merged
        questions = interview.get("questions") or []
        all_answered = all(
            str(merged.get(str(q.get("id") or ""), "")).strip() for q in questions if isinstance(q, dict)
        )
        if mark_complete and all_answered:
            interview["status"] = "complete"
            interview["completed_at"] = _now_iso()
        run["clarifier_interview"] = interview
        return run

    patch_run_meta(path, _record)
    return public_clarifier_interview(read_run_meta(path))


def _inbox_choice_label(item: dict[str, Any], choice_id: str) -> str:
    choice_id = str(choice_id or "").strip()
    if not choice_id or choice_id == "freeform":
        return str(item.get("resolved_note") or "").strip()
    for opt in item.get("options") or []:
        if not isinstance(opt, dict):
            continue
        if str(opt.get("id") or "") == choice_id:
            return str(opt.get("label") or choice_id).strip()
    return choice_id


def sync_clarifier_answers_from_inbox(folder: Path) -> dict[str, Any] | None:
    """Harvest resolved clarifier inbox items into interview answers."""
    from pathlib import Path

    from agent_lab.human_inbox import inbox_items
    from agent_lab.inbox.harvest import clarifier_harvest_key

    path = Path(folder)
    run = read_run_meta(path)
    interview = get_clarifier_interview(run)
    if not interview:
        return None
    questions = interview.get("questions") or []
    answers: dict[str, str] = {}
    for q in questions:
        if not isinstance(q, dict):
            continue
        prompt = str(q.get("prompt") or "")
        qid = str(q.get("id") or "")
        key = clarifier_harvest_key(prompt)
        for item in inbox_items(run):
            if item.get("status") != "resolved":
                continue
            item_prompt = str(item.get("prompt") or "").strip()
            key_match = item.get("harvest_key") == key
            prompt_match = item_prompt == prompt.strip()
            if not key_match and not prompt_match:
                continue
            note = str(item.get("resolved_note") or "").strip()
            choice = item.get("resolved_choice")
            selected = item.get("resolved_selected")
            answer = note
            if not answer and choice:
                answer = _inbox_choice_label(item, str(choice))
            elif not answer and selected:
                parts = selected if isinstance(selected, list) else [selected]
                answer = ", ".join(_inbox_choice_label(item, str(p)) for p in parts if p)
            if answer:
                answers[qid] = answer
                break
    if not answers:
        return public_clarifier_interview(run)
    return record_clarifier_answers(path, answers=answers)
