"""Plan CLARIFY — GJC-style multiple-choice option templates for Human Inbox."""

from __future__ import annotations

from typing import Any


def _opt(opt_id: str, label: str, description: str = "", *, recommended: bool = False) -> dict[str, Any]:
    row: dict[str, Any] = {"id": opt_id, "label": label}
    if description:
        row["description"] = description
    if recommended:
        row["recommended"] = True
    return row


def options_for_clarifier_category(category: str, *, topic: str = "") -> list[dict[str, Any]]:
    """Deterministic 3–4 choice templates per clarifier dimension (Human picks in Inbox)."""
    cat = (category or "goal").strip().lower()
    _ = topic  # reserved for future topic-aware labels

    if cat in {"goal", "priority"}:
        return [
            _opt("fix", "버그·회귀 수정", "특정 오류 재현 후 수정·검증"),
            _opt("feature", "기능 추가·개선", "새 동작 또는 UX 변경"),
            _opt("refactor", "리팩터·정리", "동작 유지, 구조·가독성 개선"),
            _opt("custom", "직접 설명", "위 선택지에 없음 — 답변에 한 줄로 적기"),
        ]
    if cat in {"scope", "context"}:
        return [
            _opt("narrow", "좁게 — 지정 경로만", "명시한 파일/모듈만 변경"),
            _opt("module", "모듈 단위", "관련 패키지·테스트 포함"),
            _opt("wide", "넓게 — 연쇄 영향 허용", "호출부·설정까지 검토"),
            _opt("custom", "직접 범위 적기", "포함/제외 경로를 답변에 적기"),
        ]
    if cat in {"verify", "criteria"}:
        return [
            _opt("pytest", "pytest", "기존/신규 테스트로 검증"),
            _opt("make", "make test / CI", "Makefile·CI 타깃으로 검증"),
            _opt("manual", "수동·시각 확인", "명령 출력·UI·로그로 확인"),
            _opt("custom", "직접 검증 기준", "명령·기대 출력을 답변에 적기"),
        ]
    if cat == "constraints":
        return [
            _opt("no_breaking", "호환 유지", "공개 API·기존 테스트 깨지 않음"),
            _opt("timebox", "시간 박스", "이번 세션에서 N action만"),
            _opt("deps", "의존성 고정", "새 패키지·메이저 업그레이드 금지"),
            _opt("custom", "직접 제약 적기", "금지 변경·의존성을 답변에 적기"),
        ]
    return [
        _opt("yes", "예 — 위 방향 맞음"),
        _opt("narrow", "더 좁게"),
        _opt("widen", "더 넓게"),
        _opt("custom", "직접 설명"),
    ]


def options_for_clarifier_question(question: dict[str, Any], *, topic: str = "") -> list[dict[str, Any]]:
    raw = question.get("options")
    if isinstance(raw, list) and len(raw) >= 2:
        return [dict(o) for o in raw if isinstance(o, dict)]
    category = str(question.get("category") or question.get("id") or "goal")
    return options_for_clarifier_category(category, topic=topic)


def attach_options_to_questions(
    questions: list[dict[str, Any]],
    *,
    topic: str = "",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        row = dict(q)
        row["options"] = options_for_clarifier_question(row, topic=topic)
        out.append(row)
    return out
