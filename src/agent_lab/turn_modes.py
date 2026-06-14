from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

UserMode = Literal["quick", "team", "loop"]
LoopTopology = Literal["route_auto", "specialist", "verified"]
PlanIntent = Literal["none", "plan_only", "loop"]


@dataclass(frozen=True, slots=True)
class ModeContractError(ValueError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class ModeContract:
    user_mode: UserMode
    runtime_turn_profile: str
    agents: list[str] | None
    agent_rounds: int
    review_mode: bool
    consensus_mode: bool
    topology: LoopTopology
    plan_intent: PlanIntent


def _clean_profile(turn_profile: str | None) -> str:
    return (turn_profile or "team").strip().lower()


def _user_mode(turn_profile: str | None) -> UserMode:
    match _clean_profile(turn_profile):
        case "quick":
            return "quick"
        case "team" | "analyze" | "discuss":
            return "team"
        case "loop" | "free" | "review" | "verified" | "specialist":
            return "loop"
        case _:
            return "team"


def _topology(turn_profile: str | None) -> LoopTopology:
    match _clean_profile(turn_profile):
        case "specialist":
            return "specialist"
        case "verified":
            return "verified"
        case _:
            return "route_auto"


def _runtime_profile(turn_profile: str | None, user_mode: UserMode) -> str:
    raw = _clean_profile(turn_profile)
    match user_mode:
        case "quick":
            return "quick"
        case "team":
            return "analyze"
        case "loop":
            match raw:
                case "specialist":
                    return "specialist"
                case "verified":
                    return "verified"
                case _:
                    return "free"


def _plan_intent(
    mode: str,
    synthesize: bool,
    user_mode: UserMode,
    turn_profile: str | None,
) -> PlanIntent:
    wants_plan = (mode or "discuss").strip().lower() == "plan" or synthesize
    match user_mode:
        case "quick":
            return "plan_only" if wants_plan else "none"
        case "team":
            return "plan_only" if wants_plan else "none"
        case "loop":
            if not wants_plan:
                raise ModeContractError("loop requires plan")
            return "loop"


def resolve_mode_contract(
    *,
    mode: str,
    synthesize: bool,
    turn_profile: str | None,
    agents: list[str] | None,
    agent_rounds: int,
    review_mode: bool,
    consensus_mode: bool,
) -> ModeContract:
    user_mode = _user_mode(turn_profile)
    plan_intent = _plan_intent(mode, synthesize, user_mode, turn_profile)
    runtime_profile = _runtime_profile(turn_profile, user_mode)
    topology = _topology(turn_profile)
    match user_mode:
        case "quick":
            return ModeContract(
                user_mode=user_mode,
                runtime_turn_profile=runtime_profile,
                agents=agents[:1] if agents else agents,
                agent_rounds=1,
                review_mode=False,
                consensus_mode=False,
                topology="route_auto",
                plan_intent=plan_intent,
            )
        case "team":
            return ModeContract(
                user_mode=user_mode,
                runtime_turn_profile=runtime_profile,
                agents=agents,
                agent_rounds=1,
                review_mode=False,
                consensus_mode=False,
                topology="route_auto",
                plan_intent=plan_intent,
            )
        case "loop":
            loop_rounds = 2 if topology == "specialist" else max(1, agent_rounds)
            return ModeContract(
                user_mode=user_mode,
                runtime_turn_profile=runtime_profile,
                agents=agents,
                agent_rounds=loop_rounds,
                review_mode=review_mode,
                consensus_mode=consensus_mode or topology == "route_auto",
                topology=topology,
                plan_intent=plan_intent,
            )


@dataclass(frozen=True, slots=True)
class LoopBudgetCaps:
    max_rounds: int
    max_calls: int
    max_token_estimate: int


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def loop_budget_caps() -> LoopBudgetCaps:
    return LoopBudgetCaps(
        max_rounds=_int_env("AGENT_LAB_LOOP_MAX_ROUNDS", 4),
        max_calls=_int_env("AGENT_LAB_LOOP_MAX_CALLS", 12),
        max_token_estimate=_int_env("AGENT_LAB_LOOP_MAX_TOKEN_EST", 500_000),
    )


def loop_budget_dict() -> dict[str, int]:
    caps = loop_budget_caps()
    return {
        "max_rounds": caps.max_rounds,
        "max_calls": caps.max_calls,
        "max_token_estimate": caps.max_token_estimate,
    }


def apply_loop_budget_caps(
    run_meta: dict[str, Any] | None,
    cap_rounds: int,
    cap_calls: int,
) -> tuple[int, int]:
    if not run_meta or str(run_meta.get("plan_intent") or "") != "loop":
        return cap_rounds, cap_calls
    budget = run_meta.get("loop_budget")
    if not isinstance(budget, dict):
        return cap_rounds, cap_calls
    if budget.get("max_rounds"):
        cap_rounds = min(cap_rounds, int(budget["max_rounds"]))
    if budget.get("max_calls"):
        cap_calls = min(cap_calls, int(budget["max_calls"]))
    return cap_rounds, cap_calls


def loop_token_budget_exceeded(
    run_meta: dict[str, Any] | None,
    context_log: list[dict[str, Any]],
) -> bool:
    if not run_meta or str(run_meta.get("plan_intent") or "") != "loop":
        return False
    budget = run_meta.get("loop_budget")
    if not isinstance(budget, dict):
        return False
    max_est = budget.get("max_token_estimate")
    if not max_est:
        return False
    from agent_lab.context_meta import summarize_turn_context

    summary = summarize_turn_context(context_log)
    chars = int(summary.get("payload_chars_total") or 0)
    token_est = chars // 4
    return token_est >= int(max_est)


def mode_contract_catalog() -> dict[str, Any]:
    """Public mode contract for GET /api/room/modes."""
    return {
        "modes": [
            {
                "id": "quick",
                "agents": "1 lead",
                "plan": "optional",
                "plan_intent": "plan_only when plan on",
                "execute_loop_on_approve": False,
            },
            {
                "id": "team",
                "agents": "selected team",
                "plan": "optional",
                "plan_intent": "plan_only when plan on",
                "execute_loop_on_approve": False,
            },
            {
                "id": "loop",
                "agents": "selected team",
                "plan": "required",
                "plan_intent": "loop",
                "execute_loop_on_approve": True,
                "budget": loop_budget_dict(),
            },
        ],
        "legacy_migration": {
            "quick": "quick",
            "analyze": "team",
            "discuss": "team",
            "free": "loop",
            "review": "loop",
            "verified": "loop",
            "specialist": "loop",
        },
        "verified_routing": {
            "ui_loop": {
                "runtime_turn_profile": "free",
                "in_turn_verified_loop": False,
                "execute_loop_on_approve": True,
            },
            "legacy_verified_api": {
                "runtime_turn_profile": "verified",
                "in_turn_verified_loop": True,
                "execute_loop_on_approve": True,
            },
            "team_plan_only": {
                "runtime_turn_profile": "analyze",
                "in_turn_verified_loop": False,
                "execute_loop_on_approve": False,
            },
        },
    }


def patch_run_mode_contract(folder: Path, contract: ModeContract) -> None:
    """Persist user-facing mode contract on the session for approval gating."""
    from agent_lab.run_meta import patch_run_meta

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        run["user_mode"] = contract.user_mode
        run["plan_intent"] = contract.plan_intent
        run["loop_topology"] = contract.topology
        if contract.plan_intent == "loop":
            run["loop_budget"] = loop_budget_dict()
        return run

    patch_run_meta(folder, _patch)


def approval_starts_execute_loop(run: dict[str, Any] | None) -> bool:
    """True when plan approval should enable mission/verified execute loops."""
    if not run:
        return True
    intent = str(run.get("plan_intent") or "").strip().lower()
    if not intent:
        # Legacy sessions predate mode contract — preserve loop-on-approve.
        return True
    return intent == "loop"
