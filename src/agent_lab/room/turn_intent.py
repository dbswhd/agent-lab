from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from agent_lab.run.state import RunStateLike

RiskLevel = Literal["low", "medium", "high"]
Confidence = Literal["low", "medium", "high"]
TaskKind = Literal["read", "code", "review", "general"]

_HIGH_RISK_MARKERS: Final[tuple[str, ...]] = (
    "결제",
    "금전",
    "거래",
    "payment",
    "financial",
    "finance",
    "security",
    "보안",
    "production",
    "프로덕션",
    "삭제",
    "delete",
    "destructive",
    "truncate",
    "drop table",
    "migration",
    "마이그레이션",
    "credential",
    "시크릿",
    "secret",
    "token",
    "revoke",
    "rotate",
    "remove",
)
_WRITE_MARKERS: Final[tuple[str, ...]] = (
    "반영",
    "실제 코드",
    "구현",
    "추가",
    "작성",
    "수정",
    "고쳐",
    "fix",
    "build",
    "patch",
)
_EXECUTE_LANE_MARKERS: Final[tuple[str, ...]] = (
    "dry-run",
    "dry run",
    "dry_run",
    "oracle pass",
    "oracle verify",
    "plan action",
    "propose_build",
    "execute lane",
    "execute",
    "merge",
    "apply",
    "worktree",
    "지금 실행",
    "실제 코드",
    "반영하고",
    "반영해",
    "실행해",
)
_BUILD_CONFIRM_MARKERS: Final[tuple[str, ...]] = (
    "구현해줘",
    "구현해주세요",
    "구현하고 테스트",
    "바로 구현",
    "진행해줘",
    "진행해주세요",
    "만들어줘",
    "만들어주세요",
    "build it",
    "implement it",
    "go ahead and implement",
)
_READ_MARKERS: Final[tuple[str, ...]] = (
    "검토",
    "분석",
    "설명",
    "확인",
    "review",
    "analyze",
    "explain",
    "어디에",
    "뭐야",
    "요약",
)
_QUICK_MARKERS: Final[tuple[str, ...]] = (
    "오타",
    "한 줄",
    "짧게",
    "단답",
    "확인만",
    "typo",
    "rename",
    "뭐야",
    "기본값",
)


@dataclass(frozen=True, slots=True)
class TurnIntent:
    """Typed evidence shared by turn selection and policy effects."""

    task_kind: TaskKind
    write_intent: bool
    execute_intent: bool
    quick_intent: bool
    route_category: str | None
    ambiguity: Confidence
    risk: RiskLevel
    evidence: tuple[str, ...]


def _has_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def is_execute_lane_topic(text: str) -> bool:
    """Return whether a topic explicitly requests the gated execute lane."""
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    if _has_marker(lowered, _EXECUTE_LANE_MARKERS):
        return True
    return "merge" in lowered and _has_marker(lowered, ("oracle", "승인", "approve", "verify"))


def is_build_confirmation_topic(text: str) -> bool:
    """Return whether a topic explicitly confirms 'implement/build this now' —
    broader than the execute-lane vocabulary in is_execute_lane_topic (which
    only matches dry-run/merge/worktree/oracle-style phrasing), narrow enough
    to skip pure explanatory questions (e.g. "구현 방법을 설명해줘")."""
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    return _has_marker(lowered, _BUILD_CONFIRM_MARKERS)


def observe_turn_intent(topic: str, run_meta: RunStateLike) -> TurnIntent:
    """Parse current and session topic into one shared turn-intent value."""
    current = (topic or "").strip().lower()
    session = str(run_meta.get("topic") or "").strip().lower()
    text = current or session
    combined = "\n".join(part for part in (current, session) if part)
    risk: RiskLevel = "high" if _has_marker(combined, _HIGH_RISK_MARKERS) else "low"
    quick_intent = _has_marker(current, _QUICK_MARKERS) or "[cat: quick]" in current
    execute_intent = is_execute_lane_topic(combined) and not (
        quick_intent and not _has_marker(current, _EXECUTE_LANE_MARKERS)
    )
    write_intent = execute_intent or _has_marker(combined, _WRITE_MARKERS)
    read_intent = _has_marker(text, _READ_MARKERS)
    task_kind: TaskKind = "code" if write_intent else "review" if read_intent else "general"
    route_category: str | None = None
    if text:
        from agent_lab.topic_router import resolve_topic_route

        route = resolve_topic_route(
            text,
            turn_profile=str(run_meta.get("turn_profile") or ""),
            session_template=str(run_meta.get("session_template") or ""),
        )
        route_category = str(route.category or "") or None
    stamped_route = run_meta.get("_turn_category")
    if isinstance(stamped_route, dict):
        route_value = str(stamped_route.get("value") or "").strip().lower()
        if route_value:
            route_category = route_value

    evidence: list[str] = []
    if risk == "high":
        evidence.append("high_risk_marker")
        if _has_marker(combined, ("금전", "거래", "payment", "financial", "finance")):
            evidence.append("financial_domain")
    if execute_intent:
        evidence.append("execute_intent")
    if write_intent:
        evidence.append("write_intent")
    if quick_intent:
        evidence.append("quick_marker")
    if read_intent:
        evidence.append("review_intent")
    if session and not current:
        evidence.append("session_topic_fallback")
    if isinstance(run_meta.get("plan_workflow"), dict):
        evidence.append("plan_workflow_state")
    if route_category:
        evidence.append(f"route_category={route_category}")

    ambiguity: Confidence = "low" if quick_intent or execute_intent else "medium"
    return TurnIntent(
        task_kind=task_kind,
        write_intent=write_intent,
        execute_intent=execute_intent,
        quick_intent=quick_intent,
        route_category=route_category,
        ambiguity=ambiguity,
        risk=risk,
        evidence=tuple(evidence),
    )
