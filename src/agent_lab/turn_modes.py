from __future__ import annotations

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


def patch_run_mode_contract(folder: Path, contract: ModeContract) -> None:
    """Persist user-facing mode contract on the session for approval gating."""
    from agent_lab.run_meta import patch_run_meta

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        run["user_mode"] = contract.user_mode
        run["plan_intent"] = contract.plan_intent
        run["loop_topology"] = contract.topology
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
