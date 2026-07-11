from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Literal

from agent_lab.run.state import RunState, RunStateLike
from agent_lab.room.turn_intent import TurnIntent, observe_turn_intent

ScribeTrigger = Literal[
    "none",
    "synthesize_only",
    "verified_loop_done",
    "consensus_reached",
    "plan_workflow_draft",
    "skill_intent",
]

TurnKind = Literal["agent_turn", "plan_side_effect"]

_PLAN_DRAFT_PHASES = frozenset({"DRAFT", "REFINE"})
_PLAN_NO_SCRIBE_PHASES = frozenset({"HUMAN_PENDING", "APPROVED"})
_PLAN_FSM_TICK_PHASES = frozenset({"INTAKE", "CLARIFY", "DRAFT", "PEER_REVIEW", "REFINE"})
_TASK_ASSIGN_PHASES = frozenset({"DRAFT", "REFINE", "PEER_REVIEW"})
_SKILL_SCRIBE_INTENTS = frozenset({"plan", "plan_draft", "ralplan", "propose_build"})


def _normalize_skill_intent(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip().lower()
    return value or None


def _route_category_from_run_meta(run_meta: RunStateLike) -> str | None:
    category = run_meta.get("_turn_category")
    if isinstance(category, dict):
        value = str(category.get("value") or "").strip().lower()
        if value:
            return value
    return None


def _preset_norm(signals: TurnSignals) -> str:
    return (signals.room_preset or "").strip().lower()


def _skip_plan_fsm_bootstrap(signals: TurnSignals) -> bool:
    if signals.skill_intent or signals.proposed_tags_count > 0 or signals.plan_execute_intent:
        return False
    return bool(
        signals.route_category == "quick"
        or signals.discuss_light
        or (signals.clarity_short_circuit and not signals.plan_execute_intent)
    )


def _is_fast_turn(signals: TurnSignals) -> bool:
    if signals.plan_execute_intent:
        return False
    if _preset_norm(signals) == "fast":
        return True
    if signals.skill_intent or signals.proposed_tags_count > 0 or signals.roster_size > 1:
        return False
    if signals.clarity_short_circuit:
        return True
    return signals.route_category == "quick" and signals.roster_size <= 1


def _is_supervisor_turn(signals: TurnSignals) -> bool:
    return not _is_fast_turn(signals) and _preset_norm(signals) != "fast"


def _skill_intent_opens_scribe(intent: str | None) -> bool:
    return _normalize_skill_intent(intent) in _SKILL_SCRIBE_INTENTS


def _proposed_envelope_threshold() -> int:
    raw = (os.getenv("AGENT_LAB_PROPOSED_SKILL_INTENT_THRESHOLD") or "").strip()
    if not raw:
        return 3
    try:
        return max(1, min(32, int(raw)))
    except ValueError:
        return 3


@dataclass(frozen=True, slots=True)
class TurnSignals:
    room_preset: str | None = None
    plan_workflow_phase: str = "INTAKE"
    plan_workflow_active: bool = False
    consensus_mode: bool = False
    consensus_status: str | None = None
    pending_agreement_count: int = 0
    verified_loop_done: bool = False
    synthesize_only: bool = False
    cancelled: bool = False
    supervisor_first_turn: bool = False
    skill_intent: str | None = None
    proposed_tags_count: int = 0
    route_category: str | None = None
    discuss_light: bool = False
    clarity_short_circuit: bool = False
    plan_execute_intent: bool = False
    roster_size: int = 0
    intent: TurnIntent | None = None

    @classmethod
    def from_run_meta(
        cls,
        run_meta: RunStateLike | None,
        *,
        room_preset: str | None = None,
        topic: str | None = None,
        consensus_meta: dict[str, Any] | None = None,
        synthesize_only: bool = False,
        cancelled: bool = False,
        verified_loop_done: bool = False,
        supervisor_first_turn: bool = False,
        skill_intent: str | None = None,
        proposed_tags_count: int = 0,
        roster_size: int | None = None,
    ) -> TurnSignals:
        from agent_lab.consensus_agreements import pending_consensus_agreements
        from agent_lab.plan.workflow import is_plan_workflow_active, plan_workflow_phase

        run = run_meta or {}
        preset = (room_preset or run.get("room_preset") or "").strip().lower() or None
        active = is_plan_workflow_active(run)
        phase = plan_workflow_phase(run) if active else "INTAKE"
        consensus = consensus_meta or {}
        status = str(consensus.get("status") or run.get("consensus_status") or "").strip().lower() or None
        pending = pending_consensus_agreements(run.get("consensus_agreements"))
        resolved_skill = _normalize_skill_intent(skill_intent) or _normalize_skill_intent(
            run.get("_active_skill_intent"),
        )
        intent = observe_turn_intent(topic or "", run)
        route_category = _route_category_from_run_meta(run) or intent.route_category
        clarity_sc = False
        if topic:
            from agent_lab.clarity import clarity_short_circuit

            clarity_sc = clarity_short_circuit(topic)
        agents_raw = run.get("agents")
        resolved_roster = (
            roster_size
            if roster_size is not None
            else (len([a for a in agents_raw if str(a).strip()]) if isinstance(agents_raw, list) else 0)
        )
        return cls(
            room_preset=preset,
            plan_workflow_phase=phase,
            plan_workflow_active=active,
            consensus_mode=bool(run.get("_active_consensus") or run.get("consensus_mode")),
            consensus_status=status,
            pending_agreement_count=len(pending),
            verified_loop_done=verified_loop_done,
            synthesize_only=synthesize_only,
            cancelled=cancelled,
            supervisor_first_turn=supervisor_first_turn,
            skill_intent=resolved_skill,
            proposed_tags_count=max(0, int(proposed_tags_count or 0)),
            route_category=route_category,
            discuss_light=bool(run.get("discuss_light")),
            clarity_short_circuit=clarity_sc,
            plan_execute_intent=intent.execute_intent,
            roster_size=max(0, int(resolved_roster)),
            intent=intent,
        )

    def routing_contract_snapshot(self) -> dict[str, Any]:
        return {
            "route_category": self.route_category,
            "discuss_light": self.discuss_light,
            "clarity_short_circuit": self.clarity_short_circuit,
            "plan_execute_intent": self.plan_execute_intent,
            "skip_fsm_bootstrap": _skip_plan_fsm_bootstrap(self),
            "fast_turn": _is_fast_turn(self),
            "supervisor_turn": _is_supervisor_turn(self),
            "roster_size": self.roster_size,
        }


@dataclass(frozen=True, slots=True)
class TurnEffects:
    run_agent_round: bool = True
    run_scribe: bool = False
    scribe_trigger: ScribeTrigger = "none"
    advance_plan_workflow: bool = False
    init_plan_workflow: bool = False
    assign_task_owners: bool = False
    turn_kind: TurnKind = "agent_turn"

    def to_turn_policy_dict(self) -> dict[str, Any]:
        return {
            "run_agent_round": self.run_agent_round,
            "run_scribe": self.run_scribe,
            "scribe_trigger": self.scribe_trigger,
            "advance_plan_workflow": self.advance_plan_workflow,
            "init_plan_workflow": self.init_plan_workflow,
            "assign_task_owners": self.assign_task_owners,
            "turn_kind": self.turn_kind,
        }


def build_turn_policy_record(
    effects: TurnEffects,
    signals: TurnSignals | None = None,
) -> dict[str, Any]:
    payload = effects.to_turn_policy_dict()
    if signals is not None:
        payload["routing_contract"] = signals.routing_contract_snapshot()
    return payload


@dataclass
class ApplyTurnEffectsResult:
    effects: TurnEffects
    applied: bool = False
    detail: str = ""
    plan_md: str = ""
    scribe_applied: bool = False
    run_meta: RunState = field(default_factory=RunState.empty)
    plan_trigger: str | None = None


class TurnPolicyEngine:
    @staticmethod
    def resolve(signals: TurnSignals) -> TurnEffects:
        if signals.cancelled:
            return TurnEffects(
                run_agent_round=not signals.synthesize_only,
                turn_kind="plan_side_effect" if signals.synthesize_only else "agent_turn",
            )
        if signals.synthesize_only:
            return TurnEffects(
                run_agent_round=False,
                run_scribe=True,
                scribe_trigger="synthesize_only",
                turn_kind="plan_side_effect",
            )

        phase = (signals.plan_workflow_phase or "INTAKE").strip().upper()
        is_fast = _is_fast_turn(signals)
        is_supervisor = _is_supervisor_turn(signals)
        skip_fsm = _skip_plan_fsm_bootstrap(signals)
        init_pw = bool(
            is_supervisor
            and signals.supervisor_first_turn
            and (not signals.plan_workflow_active or phase == "INTAKE")
            and not skip_fsm
        )
        advance_pw = bool(
            is_supervisor
            and (signals.plan_workflow_active or init_pw)
            and phase in _PLAN_FSM_TICK_PHASES
            and not skip_fsm
        )

        scribe_trigger: ScribeTrigger = "none"
        run_scribe = False
        if signals.verified_loop_done:
            run_scribe, scribe_trigger = True, "verified_loop_done"
        elif signals.consensus_status == "reached" and signals.pending_agreement_count > 0:
            run_scribe, scribe_trigger = True, "consensus_reached"
        elif not is_fast and signals.plan_workflow_active and phase in _PLAN_DRAFT_PHASES:
            run_scribe, scribe_trigger = True, "plan_workflow_draft"
        elif not is_fast and (
            _skill_intent_opens_scribe(signals.skill_intent)
            or signals.proposed_tags_count >= _proposed_envelope_threshold()
        ):
            run_scribe, scribe_trigger = True, "skill_intent"
        if phase in _PLAN_NO_SCRIBE_PHASES:
            run_scribe, scribe_trigger = False, "none"

        assign = bool(
            signals.consensus_mode or run_scribe or (signals.plan_workflow_active and phase in _TASK_ASSIGN_PHASES)
        )
        return TurnEffects(
            run_agent_round=True,
            run_scribe=run_scribe,
            scribe_trigger=scribe_trigger,
            advance_plan_workflow=advance_pw,
            init_plan_workflow=init_pw,
            assign_task_owners=assign,
            turn_kind="agent_turn",
        )
