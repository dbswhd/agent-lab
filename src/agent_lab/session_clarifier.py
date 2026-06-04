"""Minimal clarifier gate before first agent round (feature-flagged)."""

from __future__ import annotations

import os
from typing import Any


def clarifier_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_CLARIFIER") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def clarifier_min_topic_chars() -> int:
    try:
        return max(8, int(os.getenv("AGENT_LAB_CLARIFIER_MIN_CHARS", "48")))
    except ValueError:
        return 48


def _discuss_short_questions() -> list[str]:
    return [
        "이번 세션에서 가장 먼저 달성하려는 결과물은 무엇인가요? (파일·검증 기준 포함)",
        "작업 범위(레포/경로)와 제외할 영역이 있나요?",
    ]


def _discuss_first_turn_questions() -> list[str]:
    return [
        "Human이 기대하는 완료 기준(검증·산출물)을 한 줄로 적어 주세요.",
    ]


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


def build_clarifier_questions(
    topic: str,
    *,
    is_new_session: bool,
    human_message_count: int = 0,
    plan_mode: bool = False,
) -> list[str] | None:
    """Return 1–2 questions when topic is too vague to start agents."""
    if not clarifier_enabled():
        return None
    text = (topic or "").strip()
    if not text:
        return None
    short = len(text) < clarifier_min_topic_chars()
    first_turn = is_new_session and human_message_count <= 1
    if plan_mode:
        if first_turn:
            return _plan_short_questions() if short else _plan_first_turn_questions()
        if short:
            return _plan_short_questions()
        return None
    if not short and not first_turn:
        return None
    if short:
        return _discuss_short_questions()
    return _discuss_first_turn_questions()
