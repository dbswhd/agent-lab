"""Topic category routing — 합의 강도(창발 예산)를 토픽 성격에 맞게 라우팅.

LazyCodex(OmO) category routing 참고, Agent Lab 형태로 재설계:
라우팅 대상은 워커(에이전트 수·모델)가 아니라 **합의 기계의 깊이**다.
3-agent 구조는 불변, 카테고리는 debate 라운드·재조합·품질 게이트·cap을 조절한다.
오분류는 자가 치유된다 — quick/standard 턴에서 CHALLENGE/BLOCK/AMEND가 나오면
한 단계 에스컬레이션하므로 라우팅이 충돌(창발)을 억압할 수 없다.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from typing import Any, Literal

from agent_lab.room_consensus import (
    max_consensus_calls,
    max_consensus_rounds,
    max_debate_round_count,
)

Category = Literal["quick", "standard", "trading", "deep", "critical"]
Recombination = Literal["on", "auto", "off"]

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

    def category_dict(self) -> dict[str, Any]:
        """turns[].category 영속용 (additive run.json 필드)."""
        out: dict[str, Any] = {
            "value": self.category,
            "source": self.source,
            "signals": list(self.signals),
        }
        if self.escalated_from:
            out["escalated_from"] = self.escalated_from
        if self.escalation_act:
            out["escalation_act"] = self.escalation_act
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


def _build_route(
    category: Category,
    *,
    source: str,
    signals: tuple[str, ...] = (),
    efficiency_mode: bool = False,
    escalated_from: Category | None = None,
    escalation_act: str | None = None,
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
        from agent_lab.context_limits import efficiency_limits

        eff = efficiency_limits()
        max_rounds = min(max_rounds, eff.max_consensus_rounds)
        max_calls = min(max_calls, eff.max_consensus_calls)
        debate_rounds = min(debate_rounds, 2)

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
    )


def _legacy_route(*, efficiency_mode: bool = False) -> CategoryRoute:
    """라우터 off — 현행 전역 env 동작 그대로 미러 (안전 롤백 경로)."""
    from agent_lab.room_consensus import consensus_caps

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

    from agent_lab.session_clarifier import clarifier_min_topic_chars

    if len(text) < clarifier_min_topic_chars():
        return "quick", (f"len:{len(text)}",)

    return "standard", ("default",)


_PROFILE_CATEGORY: dict[str, Category] = {
    "quick": "quick",
    "verified": "critical",
    "trading": "trading",
    "analyze": "standard",
}


def resolve_topic_route(
    topic: str,
    *,
    turn_profile: str = "",
    session_template: str = "",
    efficiency_mode: bool = False,
) -> CategoryRoute:
    """marker > session template > profile 함의 > 휴리스틱 순으로 카테고리를 정하고 창발 예산을 매핑."""
    if not topic_router_enabled():
        return _legacy_route(efficiency_mode=efficiency_mode)

    marker = parse_category_marker(topic)
    if marker:
        return _build_route(
            marker,
            source="marker",
            signals=(f"marker:{marker}",),
            efficiency_mode=efficiency_mode,
        )

    template = (session_template or "").strip().lower()
    if template == "trading-mission":
        return _build_route(
            "trading",
            source="session_template",
            signals=("template:trading-mission",),
            efficiency_mode=efficiency_mode,
        )

    profile = (turn_profile or "").strip().lower()
    implied = _PROFILE_CATEGORY.get(profile)
    if implied:
        return _build_route(
            implied,
            source="profile",
            signals=(f"profile:{profile}",),
            efficiency_mode=efficiency_mode,
        )

    category, signals = classify_topic(topic)
    return _build_route(
        category,
        source="heuristic",
        signals=signals,
        efficiency_mode=efficiency_mode,
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
    """충돌 act가 라우팅을 교정 — quick→standard→deep 1단계 상승, 강등 없음."""
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
