"""Summarize plan.md changes after auto scribe."""

from __future__ import annotations

import re

_SECTION_HEADER = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

_SECTION_LABELS: dict[str, str] = {
    "지금 논의 중인 것": "지금 논의 중",
    "합의된 점": "합의된 점",
    "쟁점 / 미결정": "쟁점/미결",
    "지금 실행": "지금 실행",
    "실행 순서 (이후)": "실행 순서",
    "실행 순서": "실행 순서",
    "다음에 할 일": "다음에 할 일",
    "에이전트별 핵심": "에이전트별 핵심",
}


def _sections(plan_md: str) -> dict[str, str]:
    text = plan_md or ""
    matches = list(_SECTION_HEADER.finditer(text))
    if not matches:
        return {}
    out: dict[str, str] = {}
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[title] = text[start:end].strip()
    return out


def summarize_plan_changes(old_plan: str, new_plan: str) -> str:
    """Human-readable one-line summary of plan.md updates."""
    old_norm = (old_plan or "").strip()
    new_norm = (new_plan or "").strip()
    if not old_norm and new_norm:
        return "plan.md 신규 작성"
    if old_norm == new_norm:
        return "기존 plan과 동일 (합의 내용 이미 반영됨)"

    old_secs = _sections(old_norm)
    new_secs = _sections(new_norm)
    changed: list[str] = []
    for title, label in _SECTION_LABELS.items():
        old_body = old_secs.get(title, "")
        new_body = new_secs.get(title, "")
        if old_body != new_body and (old_body or new_body):
            changed.append(label)

    if not changed:
        for title in sorted(set(old_secs) | set(new_secs)):
            if old_secs.get(title, "") != new_secs.get(title, ""):
                changed.append(_SECTION_LABELS.get(title, title))
        changed = changed[:4]

    if not changed:
        return "plan 본문 갱신"
    if len(changed) == 1:
        return f"{changed[0]} 반영"
    if len(changed) <= 3:
        return ", ".join(changed) + " 반영"
    head = ", ".join(changed[:3])
    return f"{head} 외 {len(changed) - 3}개 섹션 반영"
