"""Topic category routing — 합의 강도(창발 예산)와 에이전트 풀을 토픽 성격에 맞게 라우팅.

LazyCodex(OmO) category routing 참고, Agent Lab 형태로 재설계:
기본 라우팅 대상은 합의 기계의 깊이(debate 라운드·재조합·품질 게이트·cap)이나,
Harness Expert Pool 패턴을 참고해 작업 유형별 에이전트 서브셋도 제안한다.
- code 작업 (구현/수정/버그): cursor + codex 우선
- review 작업 (검토/분석/평가): claude + codex 우선
- deep/critical: 서브셋 없음 (전원 참여, 다양성 최대화)
서브셋은 힌트(hint)이며 가용 에이전트가 없으면 전체 풀로 폴백한다.
오분류는 자가 치유된다 — CHALLENGE/BLOCK/AMEND 시 에스컬레이션되고 서브셋이 해제된다.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from agent_lab.room.consensus import (
    max_debate_round_count,
)

Category = Literal["quick", "standard", "trading", "deep", "critical"]
Recombination = Literal["on", "auto", "off"]
TaskType = Literal["code", "review", "general"]
TopologyHint = Literal["parallel", "producer_reviewer", "pipeline"]

CATEGORY_ORDER: tuple[Category, ...] = ("quick", "standard", "trading", "deep", "critical")
ESCALATION_ACTS = frozenset({"CHALLENGE", "BLOCK", "AMEND"})

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

_CAT_MARKER_RE = re.compile(
    r"(?:^|\n)\s*\[cat(?:egory)?\s*[:：]\s*(quick|standard|trading|deep|critical)\]",
    re.I,
)

_CRITICAL_KEYWORDS = (
    "보안",
    "security",
    "마이그레이션",
    "migration",
    "비가역",
    "irreversible",
    "데이터 삭제",
    "drop table",
    "시크릿",
    "secret",
    "credential",
    "자격증명",
    "프로덕션",
    "production",
    "결제",
    "payment",
    "권한 상승",
    "rollback 불가",
)

_DEEP_KEYWORDS = (
    "설계",
    "아키텍처",
    "architecture",
    "리팩터",
    "refactor",
    "트레이드오프",
    "trade-off",
    "tradeoff",
    "구조 개편",
    "전략",
    "strategy",
    "방식 비교",
    "장단점",
    "vs",
    "재설계",
    "redesign",
)

_TRADING_KEYWORDS = (
    "trading mission",
    "trading-mission",
    "장전",
    "premarket",
    "proposal batch",
    "proposal_batch",
    "ingest_ready",
    "trade proposal",
    "오늘 장중",
)

_QUICK_KEYWORDS = (
    "오타",
    "typo",
    "rename",
    "이름만",
    "단답",
    "짧게",
    "한 줄",
    "확인만",
    "맞아?",
    "맞나요",
    "뭐였지",
    "어디에 있",
)

# 작업 유형 키워드 — code: 구현·수정 중심, review: 분석·검토 중심
_CODE_TASK_KEYWORDS = (
    "구현",
    "implement",
    "작성해",
    "만들어",
    "추가해",
    "수정해",
    "fix",
    "build",
    "개발",
    "develop",
    "버그",
    "bug",
    "패치",
    "patch",
    "코딩",
    "coding",
    "함수",
    "function",
    "클래스",
    "class",
    "테스트 작성",
    "write test",
)

_REVIEW_TASK_KEYWORDS = (
    "리뷰",
    "review",
    "검토해",
    "분석해",
    "analyze",
    "평가해",
    "evaluate",
    "피드백",
    "feedback",
    "읽어봐",
    "봐줘",
    "어때?",
    "어떻게 생각",
    "의견",
    "opinion",
    "이해해줘",
    "explain",
    "설명해줘",
)

# 카테고리 + 작업유형 → 에이전트 서브셋 힌트 (None = 전원 참여)
# deep/critical/trading은 _resolve_agent_subset()에서 early-return None (항상 전원 참여)
_AGENT_SUBSET_MAP: dict[tuple[Category, TaskType], tuple[str, ...] | None] = {
    ("quick", "code"): ("cursor",),              # 단순 코드 작업: 가장 빠른 구현 에이전트
    ("quick", "review"): ("claude",),            # 단순 리뷰: 분석에 강한 에이전트
    ("quick", "general"): ("cursor",),           # 단순 일반: 기본 에이전트
    ("standard", "code"): ("cursor", "codex"),   # 코드 구현: 파일 편집 특화 에이전트
    ("standard", "review"): ("claude", "codex"), # 코드 리뷰: 분석 + 코드 이해
    ("standard", "general"): None,               # 일반 토론: 전원
}

# category → 창발 예산 (debate·재조합·품질 게이트·cap·wisdom)
_ROUTE_TABLE: dict[Category, dict[str, Any]] = {
    "quick": {
        "debate_rounds": 0,
        "recombination": "off",
        "quality_gate": False,
        "max_rounds": 4,
        "max_calls": 9,
        "wisdom_in_context": False,
        "suggest_verified": False,
    },
    "standard": {
        "debate_rounds": 2,
        "recombination": "auto",
        "quality_gate": False,
        "max_rounds": 8,
        "max_calls": 20,
        "wisdom_in_context": False,
        "suggest_verified": False,
    },
    "trading": {
        "debate_rounds": 2,
        "recombination": "auto",
        "quality_gate": True,
        "max_rounds": 6,
        "max_calls": 15,
        "wisdom_in_context": True,
        "suggest_verified": False,
    },
    "deep": {
        "debate_rounds": 4,
        "recombination": "on",
        "quality_gate": True,
        "max_rounds": 12,
        "max_calls": 30,
        "wisdom_in_context": True,
        "suggest_verified": False,
    },
    "critical": {
        "debate_rounds": 4,
        "recombination": "on",
        "quality_gate": True,
        "max_rounds": 12,
        "max_calls": 30,
        "wisdom_in_context": True,
        "suggest_verified": True,
    },
}


@dataclass(frozen=True)
class CategoryRoute:
    category: Category
    debate_rounds: int
    recombination: Recombination
    quality_gate: bool
    max_rounds: int
    max_calls: int
    wisdom_in_context: bool
    suggest_verified: bool
    source: str  # marker | profile | heuristic | default | disabled
    signals: tuple[str, ...] = ()
    escalated_from: Category | None = None
    escalation_act: str | None = None
    # Expert Pool 힌트: None이면 전원 참여, 값이 있으면 해당 에이전트 우선 선택
    # 에스컬레이션 시 None으로 리셋되어 자동으로 전원 참여로 복원됨
    agent_subset: tuple[str, ...] | None = None
    task_type: TaskType = "general"
    topology: TopologyHint = "parallel"
    # 역할 배정: {agent_id: role_id}, 호출측에서 active 확정 후 채워진다 (진단용 스냅샷)
    role_plan: dict[str, str] = field(default_factory=dict)

    def category_dict(self) -> dict[str, Any]:
        """turns[].category 영속용 (additive run.json 필드)."""
        out: dict[str, Any] = {
            "value": self.category,
            "source": self.source,
            "signals": list(self.signals),
            "task_type": self.task_type,
        }
        if self.escalated_from:
            out["escalated_from"] = self.escalated_from
        if self.escalation_act:
            out["escalation_act"] = self.escalation_act
        if self.agent_subset:
            out["agent_subset"] = list(self.agent_subset)
        if self.topology and self.topology != "parallel":
            out["topology"] = self.topology
        if self.role_plan:
            out["role_plan"] = dict(self.role_plan)
        return out


def topic_router_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_TOPIC_ROUTER") or "").strip().lower()
    if raw in _FALSE:
        return False
    return True


def _env_int(key: str) -> int | None:
    raw = (os.getenv(key) or "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def _trading_discuss_rounds() -> int:
    raw = (os.getenv("AGENT_LAB_TRADING_DISCUSS_ROUNDS") or "2").strip()
    try:
        return max(0, min(int(raw), 4))
    except ValueError:
        return 2


def detect_task_type(topic: str) -> TaskType:
    """토픽 텍스트에서 작업 유형을 감지 — code > review > general."""
    lower = (topic or "").lower()
    if _keyword_hits(lower, _CODE_TASK_KEYWORDS):
        return "code"
    if _keyword_hits(lower, _REVIEW_TASK_KEYWORDS):
        return "review"
    return "general"


def _resolve_agent_subset(
    category: Category,
    task_type: TaskType,
    *,
    escalated: bool = False,
) -> tuple[str, ...] | None:
    """카테고리 + 작업유형 → 에이전트 서브셋 힌트.

    에스컬레이션된 경우 또는 deep/critical에서는 항상 None(전원 참여)을 반환한다.
    """
    if escalated or category in ("deep", "critical", "trading"):
        return None
    return _AGENT_SUBSET_MAP.get((category, task_type))


def _resolve_topology(
    category: Category,
    task_type: TaskType,
    *,
    turn_profile: str = "",
    routing_hints: dict[str, Any] | None = None,
) -> TopologyHint:
    """Route-driven consensus topology (Harness pattern — not a Composer preset)."""
    hints = routing_hints or {}
    hint_topology = str(hints.get("topology") or "").strip().lower()
    if hint_topology in ("parallel", "producer_reviewer", "pipeline"):
        return hint_topology  # type: ignore[return-value]

    profile = (turn_profile or "").strip().lower()
    if profile == "specialist":
        return "producer_reviewer"

    if task_type == "review":
        return "parallel"
    if task_type == "code" and category in ("standard", "deep", "critical"):
        return "producer_reviewer"
    return "parallel"


def resolve_active_subset(
    route: CategoryRoute,
    active: list[str],
    *,
    hint: Any | None = None,
    min_agents: int = 1,
) -> tuple[list[str], tuple[str, ...] | None]:
    """Filter active agents by route subset + advisor hint (SSOT for expert pool).

    Returns (filtered_active, applied_subset). applied_subset is None when no filter applied.
    """
    subset: tuple[str, ...] | None = route.agent_subset
    if hint is not None:
        suggested: tuple[str, ...] = getattr(hint, "suggested_subset", ()) or ()
        if suggested:
            filtered = [a for a in active if str(a) in suggested]
            if filtered:
                subset = tuple(filtered)

    if not subset:
        return active, None

    pool = {str(a).strip().lower() for a in active if str(a).strip()}
    subset_active = [a for a in active if str(a).strip().lower() in subset]
    if len(subset_active) < min_agents:
        return active, None
    if len(subset_active) == len(active):
        return active, None
    return subset_active, subset


def enrich_route_with_role_plan(
    route: CategoryRoute,
    agents: list[str],
    *,
    hint: Any | None = None,
    policy: str = "auto",
) -> CategoryRoute:
    """Attach role_plan preview to route after active agents are known."""
    from agent_lab.role_plan import resolve_role_plan

    roles = resolve_role_plan(route=route, agents=agents, hint=hint, policy=policy)
    return replace(route, role_plan=roles)


def _build_route(
    category: Category,
    *,
    source: str,
    signals: tuple[str, ...] = (),
    efficiency_mode: bool = False,
    escalated_from: Category | None = None,
    escalation_act: str | None = None,
    task_type: TaskType = "general",
    turn_profile: str = "",
    routing_hints: dict[str, Any] | None = None,
) -> CategoryRoute:
    base = _ROUTE_TABLE[category]
    debate_rounds = int(base["debate_rounds"])
    if category == "trading":
        debate_rounds = _trading_discuss_rounds()
    max_rounds = int(base["max_rounds"])
    max_calls = int(base["max_calls"])

    # 명시적 전역 env는 운영자 오버라이드 — route 기본값보다 우선
    env_debate = _env_int("AGENT_LAB_DEBATE_ROUNDS")
    if env_debate is not None:
        debate_rounds = min(debate_rounds, env_debate) if category == "quick" else env_debate
    env_rounds = _env_int("AGENT_LAB_MAX_CONSENSUS_ROUNDS")
    if env_rounds is not None:
        max_rounds = env_rounds
    env_calls = _env_int("AGENT_LAB_MAX_CONSENSUS_CALLS")
    if env_calls is not None:
        max_calls = env_calls

    if efficiency_mode:
        from agent_lab.context.limits import efficiency_limits

        eff = efficiency_limits()
        max_rounds = min(max_rounds, eff.max_consensus_rounds)
        max_calls = min(max_calls, eff.max_consensus_calls)
        debate_rounds = min(debate_rounds, 2)

    agent_subset = _resolve_agent_subset(
        category, task_type, escalated=escalated_from is not None
    )
    topology = _resolve_topology(
        category,
        task_type,
        turn_profile=turn_profile,
        routing_hints=routing_hints,
    )
    if topology == "producer_reviewer":
        agent_subset = None

    return CategoryRoute(
        category=category,
        debate_rounds=debate_rounds,
        recombination=base["recombination"],
        quality_gate=bool(base["quality_gate"]),
        max_rounds=max_rounds,
        max_calls=max_calls,
        wisdom_in_context=bool(base["wisdom_in_context"]),
        suggest_verified=bool(base["suggest_verified"]),
        source=source,
        signals=signals,
        escalated_from=escalated_from,
        escalation_act=escalation_act,
        agent_subset=agent_subset,
        task_type=task_type,
        topology=topology,
    )


def _legacy_route(*, efficiency_mode: bool = False) -> CategoryRoute:
    """라우터 off — 현행 전역 env 동작 그대로 미러 (안전 롤백 경로)."""
    from agent_lab.room.consensus import consensus_caps

    cap_rounds, cap_calls = consensus_caps(efficiency_mode=efficiency_mode)
    return CategoryRoute(
        category="standard",
        debate_rounds=max_debate_round_count(efficiency_mode=efficiency_mode),
        recombination="off",
        quality_gate=False,
        max_rounds=cap_rounds,
        max_calls=cap_calls,
        wisdom_in_context=False,
        suggest_verified=False,
        source="disabled",
        agent_subset=None,
        task_type="general",
        topology="parallel",
    )


def parse_category_marker(text: str) -> Category | None:
    m = _CAT_MARKER_RE.search(text or "")
    if not m:
        return None
    return m.group(1).strip().lower()  # type: ignore[return-value]


def _keyword_hits(topic_lower: str, keywords: tuple[str, ...]) -> list[str]:
    return [kw for kw in keywords if kw in topic_lower]


def classify_topic(topic: str) -> tuple[Category, tuple[str, ...]]:
    """휴리스틱 분류 — critical > deep > quick > standard(기본)."""
    text = (topic or "").strip()
    lower = text.lower()

    critical_hits = _keyword_hits(lower, _CRITICAL_KEYWORDS)
    if critical_hits:
        return "critical", tuple(f"kw:{k}" for k in critical_hits[:4])

    trading_hits = _keyword_hits(lower, _TRADING_KEYWORDS)
    if trading_hits:
        return "trading", tuple(f"kw:{k}" for k in trading_hits[:4])

    deep_hits = _keyword_hits(lower, _DEEP_KEYWORDS)
    if deep_hits:
        return "deep", tuple(f"kw:{k}" for k in deep_hits[:4])

    quick_hits = _keyword_hits(lower, _QUICK_KEYWORDS)
    if quick_hits:
        return "quick", tuple(f"kw:{k}" for k in quick_hits[:4])

    from agent_lab.session.clarifier import clarifier_min_topic_chars

    if len(text) < clarifier_min_topic_chars():
        return "quick", (f"len:{len(text)}",)

    return "standard", ("default",)


_PROFILE_CATEGORY: dict[str, Category] = {
    "quick": "quick",
    "verified": "critical",
    "trading": "trading",
    "analyze": "standard",
}


def _routing_hints_for_template(session_template: str) -> dict[str, Any]:
    from agent_lab.session.setup import template_routing_hints

    return template_routing_hints(session_template)


def resolve_topic_route(
    topic: str,
    *,
    turn_profile: str = "",
    session_template: str = "",
    efficiency_mode: bool = False,
) -> CategoryRoute:
    """marker > session template > profile 함의 > 휴리스틱 순으로 카테고리를 정하고 창발 예산을 매핑.

    또한 토픽에서 작업 유형(code/review/general)을 감지해 Expert Pool 에이전트 서브셋 힌트를 포함한다.
    """
    if not topic_router_enabled():
        return _legacy_route(efficiency_mode=efficiency_mode)

    task_type = detect_task_type(topic)
    profile = (turn_profile or "").strip().lower()
    routing_hints = _routing_hints_for_template(session_template)

    marker = parse_category_marker(topic)
    if marker:
        return _build_route(
            marker,
            source="marker",
            signals=(f"marker:{marker}",),
            efficiency_mode=efficiency_mode,
            task_type=task_type,
            turn_profile=profile,
            routing_hints=routing_hints,
        )

    template = (session_template or "").strip().lower()
    if template == "trading-mission":
        return _build_route(
            "trading",
            source="session_template",
            signals=("template:trading-mission",),
            efficiency_mode=efficiency_mode,
            task_type=task_type,
            turn_profile=profile,
            routing_hints=routing_hints,
        )

    implied = _PROFILE_CATEGORY.get(profile)
    if implied:
        return _build_route(
            implied,
            source="profile",
            signals=(f"profile:{profile}",),
            efficiency_mode=efficiency_mode,
            task_type=task_type,
            turn_profile=profile,
            routing_hints=routing_hints,
        )

    category, signals = classify_topic(topic)
    return _build_route(
        category,
        source="heuristic",
        signals=signals,
        efficiency_mode=efficiency_mode,
        task_type=task_type,
        turn_profile=profile,
        routing_hints=routing_hints,
    )


def next_category(category: Category) -> Category:
    idx = CATEGORY_ORDER.index(category)
    if idx >= len(CATEGORY_ORDER) - 2:  # deep/critical은 상한
        return category if category == "critical" else "deep"
    return CATEGORY_ORDER[idx + 1]


def escalate_route(
    route: CategoryRoute,
    *,
    act: str,
    efficiency_mode: bool = False,
) -> CategoryRoute:
    """충돌 act가 라우팅을 교정 — quick→standard→deep 1단계 상승, 강등 없음.

    에스컬레이션 시 agent_subset을 None으로 리셋해 전원이 참여하도록 한다.
    """
    if route.source == "disabled":
        return route
    if route.category in ("deep", "critical"):
        return route
    bumped = next_category(route.category)
    escalated = _build_route(
        bumped,
        source=route.source,
        signals=route.signals,
        efficiency_mode=efficiency_mode,
        escalated_from=route.escalated_from or route.category,
        escalation_act=str(act).upper(),
        task_type=route.task_type,
        turn_profile="",
        routing_hints={"topology": route.topology} if route.topology != "parallel" else None,
    )
    # 에스컬레이션은 예산을 늘릴 수만 있다 (전역 cap 안에서)
    if escalated.max_rounds < route.max_rounds or escalated.max_calls < route.max_calls:
        escalated = replace(
            escalated,
            max_rounds=max(escalated.max_rounds, route.max_rounds),
            max_calls=max(escalated.max_calls, route.max_calls),
        )
    return escalated


def batch_escalation_act(messages: list[Any]) -> str | None:
    """배치 응답에서 첫 에스컬레이션 act (CHALLENGE > BLOCK > AMEND 우선)."""
    found: dict[str, bool] = {}
    for m in messages:
        env = getattr(m, "envelope", None)
        if not isinstance(env, dict):
            continue
        act = str(env.get("act") or "").upper()
        if act in ESCALATION_ACTS:
            found[act] = True
    for act in ("CHALLENGE", "BLOCK", "AMEND"):
        if found.get(act):
            return act
    return None


def route_debate_last(route: CategoryRoute) -> int:
    """route 기준 debate 마지막 라운드 index (room_consensus.debate_round_last 대응)."""
    if route.debate_rounds <= 0:
        return 1
    return min(1 + route.debate_rounds, route.max_rounds)
