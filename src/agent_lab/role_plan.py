"""Role orchestration — Fugu TRINITY 모티브 역할 배정 (Proposer/Critic/Synthesizer).

Pure module: I/O 없음, run.json 직접 쓰기 없음.
상태는 ephemeral run_meta["_turn_roles"] 를 통해서만 흐른다.
Kill switch: AGENT_LAB_ROOM_ROLES=0
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_lab.topic_router import CategoryRoute

_FALSE = frozenset({"0", "false", "no", "off"})


def _roles_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_ROOM_ROLES") or "").strip().lower()
    return raw not in _FALSE


@dataclass(frozen=True, slots=True)
class RoleSpec:
    id: str
    label: str
    persona: str  # 한국어 지시문, DIVERGENCE_INSTRUCTION 문체 참고


_ROLES: dict[str, RoleSpec] = {
    "proposer": RoleSpec(
        id="proposer",
        label="제안자",
        persona=(
            "[제안자 역할]\n"
            "이 라운드에서 당신은 **Proposer**입니다. "
            "가장 강한 첫 제안(`act: PROPOSE`)을 제시하세요. "
            "검토자가 도전할 표면(근거·전제·범위)을 명확히 드러내세요. "
            "비판을 소화하기 전에 조기 ENDORSE하지 마세요."
        ),
    ),
    "critic": RoleSpec(
        id="critic",
        label="검토자",
        persona=(
            "[검토자 역할]\n"
            "이 라운드에서 당신은 **Critic**입니다. "
            "제안의 약한 가정·누락·리스크 중 1건 이상을 "
            "`act: CHALLENGE` 또는 `AMEND`로 명시하세요. "
            "근거 없는 형식적 ENDORSE는 허용되지 않습니다."
        ),
    ),
    "synthesizer": RoleSpec(
        id="synthesizer",
        label="합성자",
        persona="",  # persona is resolved dynamically via recombination_follow_up()
    ),
    "executor": RoleSpec(
        id="executor",
        label="실행자",
        persona=(
            "[실행자 역할]\n"
            "이 라운드에서 당신은 **Executor**입니다. "
            "R1 발화와 CHALLENGE/AMEND를 반영한 구체적 패치·실행 제안을 "
            "`act: PROPOSE`로 제시하세요. "
            "토론 결과를 실행 가능한 단위로 번역하는 것이 당신의 역할입니다."
        ),
    ),
}

# DEFAULT_CAPABILITIES cwd_role → 기본 역할 매핑
_CWD_ROLE_TO_ROLE: dict[str, str] = {
    "primary": "proposer",  # cursor: sdk_edit, 코드 작성 주도
    "repo": "executor",     # codex: codex_cli, 구현 실행
    "review": "critic",     # claude: read_only, 리스크·검토
}


def resolve_role_plan(*, route: CategoryRoute, agents: list[str]) -> dict[str, str]:
    """카테고리·에이전트 강점 기반 역할 배정.

    - quick/trading → {} (역할 배정 없음)
    - standard → cwd_role 기반 기본 배정
    - deep → codex를 critic으로 격상 (deeper analysis)
    - critical → codex=critic + claude=synthesizer (cross-proposal synthesis)
    Kill switch: AGENT_LAB_ROOM_ROLES=0 → 항상 {}
    """
    if not _roles_enabled():
        return {}

    category = route.category
    if category in ("quick", "trading"):
        return {}

    from agent_lab.room_agent_capabilities import DEFAULT_CAPABILITIES

    result: dict[str, str] = {}
    for agent in agents:
        cap = DEFAULT_CAPABILITIES.get(agent, {})
        cwd_role = str(cap.get("cwd_role", ""))
        role = _CWD_ROLE_TO_ROLE.get(cwd_role)
        if role:
            result[agent] = role

    if category in ("deep", "critical") and "codex" in result:
        result["codex"] = "critic"

    if category == "critical" and "claude" in result:
        result["claude"] = "synthesizer"

    return result


def agent_subset_for_route(route: CategoryRoute, available: list[str]) -> list[str]:
    """토픽 카테고리별 참여 에이전트 풀.

    빈 리스트 반환 = 필터 없음 (전체 사용).
    quick만 단일 에이전트로 축소.
    """
    if not _roles_enabled():
        return []
    if route.category == "quick" and available:
        return available[:1]
    return []


def persona_for_agent(turn_roles: dict | None, agent: str) -> str:
    """turn_roles에서 에이전트 역할 페르소나 텍스트 반환. 역할 없으면 빈 문자열."""
    if not turn_roles or not agent:
        return ""
    role_id = turn_roles.get(str(agent).strip().lower(), "")
    if not role_id:
        return ""
    if role_id == "synthesizer":
        from agent_lab.room_consensus import recombination_follow_up

        return recombination_follow_up()
    spec = _ROLES.get(role_id)
    return spec.persona if spec else ""


def role_catalog() -> list[dict[str, Any]]:
    """GET /room/roles 용 역할 카탈로그."""
    return [{"id": spec.id, "label": spec.label} for spec in _ROLES.values()]
