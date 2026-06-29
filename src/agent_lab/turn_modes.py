from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

UserMode = Literal["quick", "team", "loop"]
LoopTopology = Literal["route_auto", "specialist", "verified"]
PlanIntent = Literal["none", "plan_only", "loop"]


# --- Stage-aware selective routing (AGENT_LAB_STAGE_ROUTING, default off) ---
_STAGE_ROUTING_TRUE = frozenset({"1", "true", "yes", "on"})
_PANEL_PHASES = frozenset({"DISCUSS", "PLAN_GATE", "PLAN_REJECT", "DRAFT", "PEER_REVIEW", "REFINE"})
_SOLO_PHASES = frozenset({"EXECUTE_QUEUE", "DRY_RUN", "MERGE_REVIEW", "VERIFY", "REPAIR"})


def stage_routing_enabled() -> bool:
    """AGENT_LAB_STAGE_ROUTING (default OFF): phase-aware single-vs-panel routing."""
    return (os.getenv("AGENT_LAB_STAGE_ROUTING") or "").strip().lower() in _STAGE_ROUTING_TRUE


def antidrift_enabled() -> bool:
    """AGENT_LAB_ANTIDRIFT (default OFF): structural anti-drift defenses (panel state re-injection,
    unanimity red-team, fresh-eyes audit critic seat)."""
    return (os.getenv("AGENT_LAB_ANTIDRIFT") or "").strip().lower() in {"1", "true", "yes", "on"}


def phase_default_consensus(phase: str | None) -> bool | None:
    """Phase->route table: True=panel, False=solo, None=defer to the clarity engine.

    Panel = divergence/audit phases (DISCUSS/PLAN_GATE/PLAN_REJECT/DRAFT/PEER_REVIEW/REFINE).
    Solo = convergence/execution phases (EXECUTE_QUEUE/DRY_RUN/MERGE_REVIEW/VERIFY/REPAIR).
    None = CLARIFY/INTAKE/MISSION_DEFINE/unknown so stage routing never overrides the
    clarity engine's CLARIFY decision.
    """
    p = (phase or "").strip().upper()
    if p in _PANEL_PHASES:
        return True
    if p in _SOLO_PHASES:
        return False
    return None


def stage_route_consensus(
    *,
    phase: str | None,
    turn_profile: str | None,
    consensus_mode: bool,
    stage_routing: bool | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Resolve panel-vs-solo for a turn (pure). Returns (consensus_mode, decision_log).

    Invariants: an explicit user turn_profile always wins (phase default not applied); the
    phase default applies only when STAGE_ROUTING is on, no explicit profile was chosen, and
    the phase has a non-deferring default. With stage routing off the input consensus_mode is
    returned unchanged (OFF-parity). decision_log is observational and never affects fan-out
    beyond the returned bool.
    """
    if stage_routing is None:
        stage_routing = stage_routing_enabled()
    explicit_profile = bool((turn_profile or "").strip())
    phase_default = phase_default_consensus(phase) if stage_routing else None
    applied = bool(stage_routing and not explicit_profile and phase_default is not None)
    resolved = phase_default if applied else consensus_mode
    log: dict[str, Any] = {
        "phase": (phase or "").strip().upper() or None,
        "stage_routing": bool(stage_routing),
        "explicit_profile": explicit_profile,
        "phase_default": phase_default,
        "applied": applied,
        "consensus_mode": bool(resolved),
    }
    return bool(resolved), log


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
    divergence: bool = False


def _clean_profile(turn_profile: str | None) -> str:
    return (turn_profile or "team").strip().lower()


def _is_divergence(turn_profile: str | None) -> bool:
    return _clean_profile(turn_profile) in ("divergence", "발산")


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
                try:
                    from agent_lab.room.turn_policy import turn_policy_enabled

                    if turn_policy_enabled():
                        return "loop"
                except ImportError:
                    pass
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
    if _is_divergence(turn_profile):
        return ModeContract(
            user_mode="team",
            runtime_turn_profile="divergence",
            agents=agents,
            agent_rounds=max(1, agent_rounds),
            review_mode=False,
            consensus_mode=False,
            topology="route_auto",
            plan_intent="none",
            divergence=True,
        )
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


def loop_max_cost_tier() -> str:
    raw = (os.getenv("AGENT_LAB_LOOP_MAX_COST_TIER") or "high").strip().lower()
    if raw in ("low", "medium", "high"):
        return raw
    return "high"


def loop_budget_dict() -> dict[str, int | str]:
    caps = loop_budget_caps()
    return {
        "max_rounds": caps.max_rounds,
        "max_calls": caps.max_calls,
        "max_token_estimate": caps.max_token_estimate,
        "max_cost_tier": loop_max_cost_tier(),
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
    from agent_lab.context.meta import summarize_turn_context

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
            {
                "id": "divergence",
                "agents": "selected team (parallel, independent)",
                "plan": "none",
                "plan_intent": "none",
                "execute_loop_on_approve": False,
                "divergence": True,
                "options": "2-4 approach-distinct alternatives; stops at options list",
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
            "divergence": "divergence",
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
    from agent_lab.run.meta import patch_run_meta

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        run["user_mode"] = contract.user_mode
        run["plan_intent"] = contract.plan_intent
        run["loop_topology"] = contract.topology
        run["divergence_mode"] = contract.divergence
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
