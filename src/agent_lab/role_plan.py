"""Role orchestration — Fugu TRINITY 모티브 역할 배정 (Proposer/Critic/Synthesizer).

Pure module: I/O 없음, run.json 직접 쓰기 없음.
상태는 ephemeral run_meta ``_turn_roles`` 를 통해서만 흐른다.
Kill switch: AGENT_LAB_ROOM_ROLES=0
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Sequence

from agent_lab.run.state import RunStateLike

if TYPE_CHECKING:
    from agent_lab.topic_router import CategoryRoute

RolePolicy = Literal["auto", "force", "off"]

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
    "delegator": RoleSpec(
        id="delegator",
        label="위임자",
        persona=(
            "[Delegator · supervisor preset]\n"
            "Harness Supervisor seat: 턴 리드로 phase/GO를 제안하고, "
            "peer에게 scoped review를 위임하세요. execute는 cursor에, "
            "decompose/verify는 codex에, blind-spot review는 claude에 맡기세요. "
            "Human gate·fork·BLOCK은 Human에게만 올리세요. "
            "동료 위임 시 envelope `act: MESSAGE`, `to: <agent>`를 사용하세요."
        ),
    ),
}

# DEFAULT_CAPABILITIES cwd_role → 기본 역할 매핑
_CWD_ROLE_TO_ROLE: dict[str, str] = {
    "primary": "proposer",  # cursor: sdk_edit, 코드 작성 주도
    "repo": "executor",  # codex: codex_cli, 구현 실행
    "review": "critic",  # claude: read_only, 리스크·검토
}


def _apply_hint_overrides(result: dict[str, str], agents: list[str], hint: Any | None) -> dict[str, str]:
    if hint is None:
        return result
    overrides: dict[str, str] = getattr(hint, "role_overrides", {}) or {}
    for agent, role_id in overrides.items():
        if agent in agents and role_id in _ROLES:
            result[agent] = role_id
    return result


def _task_type_role_plan(task_type: str, agents: list[str]) -> dict[str, str]:
    """Task-type matrix from ROLE-ORCHESTRATION-PLAN §P1."""
    pool = [str(a).strip().lower() for a in agents if str(a).strip()]
    result: dict[str, str] = {}
    if task_type == "code":
        if "cursor" in pool:
            result["cursor"] = "executor"
        if "claude" in pool:
            result["claude"] = "critic"
        if "codex" in pool:
            result["codex"] = "proposer"
    elif task_type == "review":
        if "claude" in pool:
            result["claude"] = "proposer"
        for agent in pool:
            if agent != "claude" and agent not in result:
                result[agent] = "critic"
    return result


def _merge_role_plans(*plans: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for plan in plans:
        merged.update(plan)
    return merged


def stamp_review_advocate_role(
    run_meta: RunStateLike,
    agents: list[str],
    human_turn_index: int,
) -> str | None:
    """Review mode: rotate devil's advocate into _turn_roles critic (P5b)."""
    if not _roles_enabled() or not agents:
        return None
    advocate = str(agents[human_turn_index % len(agents)]).strip().lower()
    roles = dict(run_meta.get("_turn_roles") or {})
    roles[advocate] = "critic"
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, _turn_roles=roles)
    return advocate


def review_follow_up_uses_role_persona(run_meta: RunStateLike | None, advocate: str | None) -> bool:
    """True when critic persona in reply_policy replaces legacy review_advocate follow-up."""
    if not advocate or not run_meta:
        return False
    if not _roles_enabled():
        return False
    roles = run_meta.get("_turn_roles") or {}
    return roles.get(str(advocate).strip().lower()) == "critic"


def resolve_review_advocate(
    agents: Sequence[str],
    human_turn_index: int,
    *,
    run_meta: RunStateLike | None = None,
    review_mode: bool = False,
) -> str | None:
    """Legacy review_advocate seam — critic from _turn_roles when roles enabled."""
    if not review_mode or not agents:
        return None
    if _roles_enabled() and run_meta:
        roles = run_meta.get("_turn_roles") or {}
        for agent in agents:
            if roles.get(str(agent).strip().lower()) == "critic":
                return str(agent).strip().lower()
        advocate = stamp_review_advocate_role(run_meta, agents, human_turn_index)
        return advocate
    from agent_lab.room.messages import _review_advocate

    return str(_review_advocate(agents, human_turn_index)).strip().lower()


def _cwd_role_plan(agents: list[str]) -> dict[str, str]:
    from agent_lab.room.agent_capabilities import DEFAULT_CAPABILITIES

    result: dict[str, str] = {}
    for agent in agents:
        cap = DEFAULT_CAPABILITIES.get(agent, {})
        cwd_role = str(cap.get("cwd_role", ""))
        role = _CWD_ROLE_TO_ROLE.get(cwd_role)
        if role:
            result[agent] = role
    return result


def _force_role_plan(agents: list[str], hint: Any | None = None) -> dict[str, str]:
    """Proposer/Critic (etc.) from cwd_role — ignores quick/trading category skips."""
    from agent_lab.room.agent_capabilities import DEFAULT_CAPABILITIES

    result = _cwd_role_plan(agents)
    if len(agents) >= 2 and "proposer" not in result.values():
        for agent in agents:
            cap = DEFAULT_CAPABILITIES.get(agent, {})
            if str(cap.get("cwd_role") or "").strip().lower() == "primary":
                result.setdefault(agent, "proposer")
                break
        else:
            result.setdefault(agents[0], "proposer")
        for agent in agents[1:]:
            if agent not in result:
                result[agent] = "critic"
                break
    return _apply_hint_overrides(result, agents, hint)


def resolve_role_plan(
    *,
    route: CategoryRoute,
    agents: list[str],
    hint: Any | None = None,
    policy: RolePolicy | str = "auto",
) -> dict[str, str]:
    """카테고리·에이전트 강점 기반 역할 배정.

    policy:
    - auto: category + cwd_role + advisor (quick/trading → {})
    - force: cwd_role Proposer/Critic always (category skip ignored)
    - off: always {}

    Kill switch: AGENT_LAB_ROOM_ROLES=0 → always {}

    hint: optional SetupHint from feedback_advisor (Phase B).
    hint.role_overrides가 있으면 기본 배정을 agent 단위로 override.
    """
    policy_norm = str(policy or "auto").strip().lower()
    if policy_norm == "off" or not _roles_enabled():
        return {}
    if policy_norm == "force":
        return _force_role_plan(agents, hint=hint)

    category = route.category
    if category in ("quick", "trading"):
        return {}

    task_type = getattr(route, "task_type", "general") or "general"
    result = _merge_role_plans(_cwd_role_plan(agents), _task_type_role_plan(task_type, agents))

    if category in ("deep", "critical"):
        for agent in agents:
            if agent not in result:
                continue
            if category == "critical" and agent == "claude":
                result[agent] = "synthesizer"
            elif agent == "codex" and result.get(agent) != "synthesizer":
                result[agent] = "critic"

    return _apply_hint_overrides(result, agents, hint)


def resolve_delegator_agent(
    agents: list[str],
    *,
    run_meta: RunStateLike | None = None,
) -> str:
    """Supervisor preset delegator seat (default codex)."""
    _ = run_meta
    raw = (os.getenv("SUPERVISOR_DELEGATOR") or "codex").strip().lower()
    pool = [str(a).strip().lower() for a in agents if str(a).strip()]
    if raw in pool:
        return raw
    for fallback in ("codex", "cursor", "claude"):
        if fallback in pool:
            return fallback
    return pool[0] if pool else "codex"


def _is_supervisor_turn(run_meta: RunStateLike) -> bool:
    """Prefer the TurnPolicy-stamped signal over raw ``room_preset`` (TurnContract §8.2 P2).

    Delegator overrides must not leak onto turns TurnContract classified as fast — see
    ``supervisor_turn_from_run_meta`` for why the raw preset can no longer tell them apart.
    """
    from agent_lab.room.turn_policy import is_supervisor_turn_with_preset_fallback

    preset = str(run_meta.get("room_preset") or "").strip().lower()
    return is_supervisor_turn_with_preset_fallback(run_meta, room_preset=preset)


def apply_preset_role_overrides(
    run_meta: RunStateLike,
    roles: dict[str, str],
    agents: list[str],
) -> dict[str, str]:
    """Stamp supervisor delegator + team_lead without adding a new agent id."""
    if not _is_supervisor_turn(run_meta):
        return roles
    delegator = resolve_delegator_agent(agents, run_meta=run_meta)
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, team_lead=delegator)
    if not _roles_enabled():
        return roles
    result = dict(roles)
    result[delegator] = "delegator"
    return result


def agent_subset_for_route(
    route: CategoryRoute,
    available: list[str],
    hint: Any | None = None,
) -> list[str]:
    """토픽 카테고리별 참여 에이전트 풀 — topic_router.resolve_active_subset SSOT.

    빈 리스트 반환 = 필터 없음 (전체 사용).
    """
    if not _roles_enabled():
        return []

    from agent_lab.topic_router import resolve_active_subset

    filtered, applied = resolve_active_subset(route, available, hint=hint, min_agents=1)
    if not applied:
        return []
    return filtered


def persona_for_agent(turn_roles: dict | None, agent: str, *, run_meta: RunStateLike | None = None) -> str:
    """turn_roles에서 에이전트 역할 페르소나 텍스트 반환. 역할 없으면 빈 문자열."""
    if not turn_roles or not agent:
        return ""
    role_id = turn_roles.get(str(agent).strip().lower(), "")
    if not role_id:
        return ""
    if role_id == "synthesizer":
        from agent_lab.room.consensus import recombination_follow_up

        return recombination_follow_up()
    if role_id == "delegator":
        from agent_lab.room.roster_context import active_agents_from_run_meta, delegator_persona

        return delegator_persona(active_agents_from_run_meta(run_meta))
    spec = _ROLES.get(role_id)
    return spec.persona if spec else ""


def role_catalog() -> list[dict[str, Any]]:
    """GET /room/roles 용 역할 카탈로그."""
    return [{"id": spec.id, "label": spec.label} for spec in _ROLES.values()]
