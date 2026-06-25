"""Agent role orchestration — per-turn persona assignments composited on the consensus loop.

역할은 페르소나 텍스트일 뿐: anchor/AMEND/ENDORSE 합의 기계는 불변.
에스컬레이션 시 역할이 해제되어 전원 자유토론으로 복귀한다 (모트 보존).
킬스위치: AGENT_LAB_ROOM_ROLES=0
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_lab.topic_router import CategoryRoute


@dataclass(frozen=True, slots=True)
class RoleSpec:
    id: str
    label: str
    persona: str


def _build_roles() -> dict[str, RoleSpec]:
    from agent_lab.room_consensus import recombination_follow_up

    return {
        "proposer": RoleSpec(
            id="proposer",
            label="제안자",
            persona=(
                "[역할: 제안자(Proposer)]\n"
                "이 턴에서 당신은 제안자입니다. 강한 1차 PROPOSE안을 작성하세요 — "
                "조기 합의를 추구하지 말고 근거와 취약점을 명시적으로 노출해 "
                "검토자가 검증할 수 있도록 하세요. envelope `act: PROPOSE`를 사용하세요."
            ),
        ),
        "critic": RoleSpec(
            id="critic",
            label="검토자",
            persona=(
                "[역할: 검토자(Critic)]\n"
                "이 턴에서 당신은 검토자입니다. 제안의 약한 가정이나 누락된 리스크 1건 이상을 "
                "찾아 CHALLENGE 또는 AMEND envelope로 실질적 반론을 제시하세요. "
                "형식적 동의는 금지 — 진짜 이견이 없으면 근거를 한 줄로 밝히고 ENDORSE 하세요."
            ),
        ),
        "synthesizer": RoleSpec(
            id="synthesizer",
            label="합성자",
            persona=recombination_follow_up(),  # 재조합 라운드 = 합성자 매핑 고정
        ),
        "executor": RoleSpec(
            id="executor",
            label="실행자",
            persona=(
                "[역할: 실행자(Executor)]\n"
                "이 턴에서 당신은 실행자입니다. 합의된 방향을 패치·실행으로 구체화하세요 — "
                "R1 발화와 CHALLENGE를 반영해 실제 변경 제안을 만드세요. "
                "계획보다 실행, 논의보다 코드 변경을 우선합니다."
            ),
        ),
    }


# lazy-init so room_consensus import doesn't trigger at early module scan
_ROLES: dict[str, RoleSpec] | None = None


def _get_roles() -> dict[str, RoleSpec]:
    global _ROLES  # noqa: PLW0603
    if _ROLES is None:
        _ROLES = _build_roles()
    return _ROLES


def _room_roles_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_ROOM_ROLES") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def resolve_role_plan(*, route: CategoryRoute, agents: list[str]) -> dict[str, str]:
    """topic_router CategoryRoute + active agent list → {agent_id: role_id}.

    Returns {} (no roles, pure emergence) when:
    - AGENT_LAB_ROOM_ROLES=0
    - category is "quick" (single/lightweight)
    - agent list is empty
    - task_type is "general" and category is not deep/critical
    """
    if not _room_roles_enabled():
        return {}
    if not agents:
        return {}
    if route.category == "quick":
        return {}

    task_type = route.task_type
    category = route.category
    result: dict[str, str] = {}

    if task_type == "code":
        # cursor = primary implementer (proposer); claude = reviewer (critic); codex = verifier (critic)
        for a in agents:
            a_norm = str(a).strip().lower()
            if a_norm == "cursor":
                result[a_norm] = "proposer"
            elif a_norm == "claude":
                result[a_norm] = "critic"
            elif a_norm == "codex":
                result[a_norm] = "critic"
            else:
                result[a_norm] = "proposer"
        # deep/critical code: cursor stays proposer, but all others are critics
        if category in ("deep", "critical"):
            for a_norm, role in list(result.items()):
                if a_norm != "cursor":
                    result[a_norm] = "critic"

    elif task_type == "review":
        # claude = primary reviewer (proposer); everyone else = critic
        for a in agents:
            a_norm = str(a).strip().lower()
            result[a_norm] = "proposer" if a_norm == "claude" else "critic"

    elif category in ("deep", "critical"):
        # general deep/critical: first agent proposes, rest critique
        ordered = [str(a).strip().lower() for a in agents]
        for i, a_norm in enumerate(ordered):
            result[a_norm] = "proposer" if i == 0 else "critic"

    # general + standard/trading → {} (pure emergence, no static roles)

    return result


def persona_for_agent(turn_roles: dict[str, str] | None, agent: str) -> str:
    """Return persona guidance text for a specific agent, or '' if no role assigned."""
    if not turn_roles or not agent:
        return ""
    role_id = turn_roles.get(str(agent).strip().lower(), "")
    if not role_id:
        return ""
    spec = _get_roles().get(role_id)
    return spec.persona if spec else ""


def role_catalog() -> dict[str, object]:
    """Return role info for /api/room/roles."""
    return {
        "roles": [
            {"id": spec.id, "label": spec.label, "persona_preview": spec.persona[:120]}
            for spec in _get_roles().values()
        ]
    }
