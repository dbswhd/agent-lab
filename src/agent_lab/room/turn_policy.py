"""TurnPolicy — signal-driven Room turn side effects (Wave F).

Replaces Plan toggle / ``synthesize`` as the authority for Scribe, plan_workflow tick,
and task assign. See docs/TURN-POLICY.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ScribeTrigger = Literal[
    "none",
    "synthesize_only",
    "verified_loop_done",
    "consensus_reached",
    "plan_workflow_draft",
    "legacy_plan_send",
]

TurnKind = Literal["agent_turn", "plan_side_effect"]

_PLAN_DRAFT_PHASES = frozenset({"DRAFT", "REFINE"})
_PLAN_NO_SCRIBE_PHASES = frozenset({"HUMAN_PENDING", "APPROVED"})
_PLAN_FSM_TICK_PHASES = frozenset({"INTAKE", "CLARIFY", "DRAFT", "PEER_REVIEW", "REFINE"})
_TASK_ASSIGN_PHASES = frozenset({"DRAFT", "REFINE", "PEER_REVIEW"})


def turn_policy_enabled() -> bool:
    """``AGENT_LAB_TURN_POLICY=1`` — default on (Wave F4). Set ``0`` for legacy path."""
    raw = (os.getenv("AGENT_LAB_TURN_POLICY") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


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
    legacy_synthesize_hint: bool = False

    @classmethod
    def from_run_meta(
        cls,
        run_meta: dict[str, Any] | None,
        *,
        room_preset: str | None = None,
        consensus_meta: dict[str, Any] | None = None,
        synthesize_only: bool = False,
        cancelled: bool = False,
        legacy_synthesize_hint: bool = False,
        verified_loop_done: bool = False,
        supervisor_first_turn: bool = False,
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
            legacy_synthesize_hint=legacy_synthesize_hint,
        )


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


@dataclass
class ApplyTurnEffectsResult:
    effects: TurnEffects
    applied: bool = False
    detail: str = ""
    plan_md: str = ""
    scribe_applied: bool = False
    run_meta: dict[str, Any] = field(default_factory=dict)
    plan_trigger: str | None = None


class TurnPolicyEngine:
    """Pure resolver — decision table SSOT: docs/TURN-POLICY.md."""

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

        preset = (signals.room_preset or "").strip().lower()
        phase = (signals.plan_workflow_phase or "INTAKE").strip().upper()
        is_fast = preset == "fast"
        is_supervisor = preset == "supervisor"

        init_pw = bool(
            is_supervisor
            and signals.supervisor_first_turn
            and (not signals.plan_workflow_active or phase == "INTAKE")
        )

        advance_pw = bool(
            is_supervisor
            and not is_fast
            and (signals.plan_workflow_active or init_pw)
            and phase in _PLAN_FSM_TICK_PHASES
        ) or bool(
            signals.legacy_synthesize_hint
            and signals.plan_workflow_active
            and phase in _PLAN_FSM_TICK_PHASES
        )

        scribe_trigger: ScribeTrigger = "none"
        run_scribe = False

        if signals.verified_loop_done:
            run_scribe = True
            scribe_trigger = "verified_loop_done"
        elif signals.consensus_status == "reached" and signals.pending_agreement_count > 0:
            run_scribe = True
            scribe_trigger = "consensus_reached"
        elif (
            not is_fast
            and signals.plan_workflow_active
            and phase in _PLAN_DRAFT_PHASES
            and phase not in _PLAN_NO_SCRIBE_PHASES
        ):
            run_scribe = True
            scribe_trigger = "plan_workflow_draft"
        elif signals.legacy_synthesize_hint and not is_fast:
            run_scribe = True
            scribe_trigger = "legacy_plan_send"

        if is_fast and not signals.synthesize_only:
            run_scribe = False
            scribe_trigger = "none"

        if phase in _PLAN_NO_SCRIBE_PHASES:
            run_scribe = False
            scribe_trigger = "none"

        assign = bool(
            signals.consensus_mode
            or run_scribe
            or (signals.plan_workflow_active and phase in _TASK_ASSIGN_PHASES)
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


def prepare_turn_policy_before_agent_round(
    folder: Path,
    run_meta: dict[str, Any],
    *,
    synthesize: bool,
    human_turn: int,
) -> tuple[dict[str, Any], TurnEffects | None]:
    """Resolve and persist TurnEffects before agent round; bootstrap FSM when needed."""
    if not turn_policy_enabled():
        return run_meta, None
    from agent_lab.plan.workflow import (
        init_plan_workflow_on_plan_send,
        is_plan_workflow_active,
    )
    from agent_lab.run.meta import read_run_meta

    signals = TurnSignals.from_run_meta(
        run_meta,
        legacy_synthesize_hint=synthesize,
        supervisor_first_turn=human_turn <= 1,
    )
    room_preset_hint = signals.room_preset
    effects = TurnPolicyEngine.resolve(signals)
    persist_turn_policy_on_run_meta(run_meta, effects)
    if folder.is_dir() and effects.init_plan_workflow and not is_plan_workflow_active(run_meta):
        init_plan_workflow_on_plan_send(folder)
        run_meta = read_run_meta(folder)
        signals = TurnSignals.from_run_meta(
            run_meta,
            room_preset=room_preset_hint,
            legacy_synthesize_hint=synthesize,
            supervisor_first_turn=human_turn <= 1,
        )
        effects = TurnPolicyEngine.resolve(signals)
        persist_turn_policy_on_run_meta(run_meta, effects)
    snap_tp = run_meta.get("turn_policy")
    snap_tk = run_meta.get("turn_kind")
    snap_rp = run_meta.get("room_preset") or room_preset_hint
    if folder.is_dir() and (isinstance(snap_tp, dict) or snap_tk or snap_rp):
        from agent_lab.run.meta import patch_run_meta

        def _persist(run: dict[str, Any]) -> dict[str, Any]:
            if isinstance(snap_tp, dict):
                run["turn_policy"] = snap_tp
            if snap_tk:
                run["turn_kind"] = snap_tk
            if snap_rp:
                run["room_preset"] = snap_rp
            return run

        patch_run_meta(folder, _persist)
    return run_meta, effects


def should_assign_tasks_for_run_meta(run_meta: dict[str, Any] | None) -> bool:
    """Task assign gate — TurnPolicy snapshot or legacy mode/synthesize."""
    run = run_meta or {}
    tp = run.get("turn_policy")
    if isinstance(tp, dict) and turn_policy_enabled():
        return bool(tp.get("assign_task_owners"))
    from agent_lab.room.team_orchestration import should_assign_tasks_on_turn

    return should_assign_tasks_on_turn(
        mode=str(run.get("_active_turn_mode") or "discuss"),
        synthesize=bool(run.get("_active_synthesize")),
        consensus_mode=bool(run.get("_active_consensus") or run.get("consensus_mode")),
    )


def is_discuss_only_for_run_meta(run_meta: dict[str, Any] | None) -> bool:
    """Discuss-only task harvest — inverse of assign_task_owners when TurnPolicy ON."""
    if turn_policy_enabled() and run_meta:
        tp = run_meta.get("turn_policy")
        if isinstance(tp, dict):
            return not bool(tp.get("assign_task_owners"))
    from agent_lab.room.team_orchestration import is_discuss_only_turn

    run = run_meta or {}
    return is_discuss_only_turn(
        mode=str(run.get("_active_turn_mode") or "discuss"),
        synthesize=bool(run.get("_active_synthesize")),
        consensus_mode=bool(run.get("_active_consensus") or run.get("consensus_mode")),
    )


def persist_turn_policy_on_run_meta(run_meta: dict[str, Any], effects: TurnEffects) -> None:
    run_meta["turn_policy"] = effects.to_turn_policy_dict()
    run_meta["turn_kind"] = effects.turn_kind


def assign_task_owners_from_run_meta(run_meta: dict[str, Any] | None) -> bool | None:
    """Read persisted ``turn_policy.assign_task_owners`` snapshot; None if absent."""
    tp = (run_meta or {}).get("turn_policy")
    if isinstance(tp, dict) and "assign_task_owners" in tp:
        return bool(tp.get("assign_task_owners"))
    return None


def _scribe_idempotency_key(human_turn: int, trigger: ScribeTrigger) -> str:
    return f"{human_turn}:{trigger}"


def _already_scribed(run_meta: dict[str, Any], key: str) -> bool:
    applied = run_meta.get("_turn_policy_scribe_keys") or []
    if not isinstance(applied, list):
        return False
    return key in applied


def _mark_scribed(run_meta: dict[str, Any], key: str) -> None:
    applied = list(run_meta.get("_turn_policy_scribe_keys") or [])
    if key not in applied:
        applied.append(key)
    run_meta["_turn_policy_scribe_keys"] = applied


def _plan_trigger_for_scribe(trigger: ScribeTrigger, *, legacy_synthesize: bool) -> str:
    if trigger == "legacy_plan_send":
        return "plan_turn"
    if trigger == "plan_workflow_draft":
        return "auto_turn"
    if trigger in ("consensus_reached", "verified_loop_done", "synthesize_only"):
        return trigger
    return "plan_turn" if legacy_synthesize else "auto_turn"


def _run_fsm_tick(
    folder: Path,
    *,
    run_meta: dict[str, Any],
    plan_md: str,
    plan_before: str,
    synthesize: bool,
    cancelled: bool,
    on_event: Any,
) -> tuple[str, dict[str, Any], bool]:
    """Tick plan FSM; return (plan_md, run_meta, pw_force_scribe)."""
    from agent_lab.human_inbox import has_pending_question
    from agent_lab.plan.workflow import (
        is_plan_workflow_active,
        plan_workflow_should_advance_on_turn,
        tick_plan_workflow_after_turn,
    )
    from agent_lab.room.agent_invoke import _bind_session_to_run_meta
    from agent_lab.room.session_persist import _session_context

    pw_force_scribe = False
    pw_active = is_plan_workflow_active(run_meta)
    if turn_policy_enabled():
        pw_advance = pw_active
    else:
        pw_advance = plan_workflow_should_advance_on_turn(run_meta, synthesize=synthesize)
    if pw_active and pw_advance and not cancelled:
        pw_tick = tick_plan_workflow_after_turn(
            folder,
            synthesize=synthesize,
            cancelled=cancelled,
            plan_md=plan_md,
            plan_before=plan_before,
            has_pending_inbox_question=has_pending_question(run_meta),
            turn_policy_advance=turn_policy_enabled(),
        )
        if pw_tick.get("wait_inbox") and on_event:
            on_event("inbox_pending", {"phase": "CLARIFY"})
        if pw_tick.get("advance") == "DRAFT":
            pw_force_scribe = True
        plan_md, run_meta = _session_context(folder)
        _bind_session_to_run_meta(run_meta, folder)
    return plan_md, run_meta, pw_force_scribe


def _run_turn_policy_scribe(
    *,
    folder: Path,
    topic: str,
    messages: list[Any],
    run_meta: dict[str, Any],
    plan_before: str,
    mode: str,
    effects: TurnEffects,
    legacy_synthesize: bool,
    cancelled: bool,
    on_event: Any,
    permissions: dict | None,
    consensus_meta: dict[str, Any] | None,
    verified_result: dict[str, Any] | None,
    human_turn: int,
    pw_force_scribe: bool,
) -> tuple[str, bool, str | None]:
    from agent_lab.room.plan_scribe import _apply_scribe_after_turn
    from agent_lab.room.turn_meta import (
        maybe_auto_scribe_after_consensus,
        maybe_auto_scribe_after_verified_loop,
    )

    trigger = effects.scribe_trigger
    if cancelled or (not effects.run_scribe and not pw_force_scribe):
        return plan_before, False, None

    if pw_force_scribe and trigger == "none":
        trigger = "plan_workflow_draft"

    idem_key = _scribe_idempotency_key(human_turn, trigger)
    if _already_scribed(run_meta, idem_key):
        plan_path = folder / "plan.md"
        current = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else plan_before
        return current, False, None

    plan_md = plan_before
    scribe_applied = False
    plan_trigger = _plan_trigger_for_scribe(trigger, legacy_synthesize=legacy_synthesize)

    if trigger == "consensus_reached":
        auto = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta=consensus_meta,
            synthesize=legacy_synthesize,
            cancelled=cancelled,
            on_event=on_event,
            permissions=permissions,
        )
        if auto is not None:
            plan_md = auto
            scribe_applied = plan_md != plan_before
    elif trigger == "verified_loop_done":
        auto = maybe_auto_scribe_after_verified_loop(
            folder,
            verified_result=verified_result,
            cancelled=cancelled,
            on_event=on_event,
            permissions=permissions,
        )
        if auto is not None:
            plan_md = auto
            scribe_applied = True
    elif trigger == "synthesize_only":
        room = __import__("agent_lab.room", fromlist=["synthesize_session_plan"])
        plan_md, _summary = room.synthesize_session_plan(
            folder,
            on_event=on_event,
            permissions=permissions,
            trigger="synthesize_only",
            previous_plan_md=plan_before,
        )
        scribe_applied = bool(plan_md)
    else:
        plan_md = _apply_scribe_after_turn(
            topic=topic,
            messages=messages,
            run_meta=run_meta,
            plan_before=plan_before,
            mode=mode,
            scribe=True,
            user_plan_send=legacy_synthesize or trigger == "legacy_plan_send",
            cancelled=cancelled,
            on_event=on_event,
            session_folder=folder,
            plan_trigger=plan_trigger,
        )
        scribe_applied = bool(plan_md and plan_md != plan_before) or trigger in (
            "plan_workflow_draft",
            "legacy_plan_send",
        )

    if scribe_applied or (plan_md and plan_md != plan_before):
        _mark_scribed(run_meta, idem_key)
        scribe_applied = True

    return plan_md, scribe_applied, plan_trigger


def apply_turn_effects(
    *,
    signals: TurnSignals,
    folder: Path | None = None,
    topic: str = "",
    messages: list[Any] | None = None,
    run_meta: dict[str, Any] | None = None,
    plan_before: str = "",
    mode: str = "discuss",
    legacy_synthesize: bool = False,
    cancelled: bool = False,
    active_agents: list[Any] | None = None,
    permissions: dict | None = None,
    on_event: Any = None,
    consensus_meta: dict[str, Any] | None = None,
    verified_result: dict[str, Any] | None = None,
    human_turn: int = 0,
    skip_fsm: bool = False,
    skip_peer_pipeline: bool = False,
    **_kwargs: Any,
) -> ApplyTurnEffectsResult:
    """Single choke for Scribe / FSM / tasks when ``AGENT_LAB_TURN_POLICY=1``."""
    effects = TurnPolicyEngine.resolve(signals)
    meta = dict(run_meta or {})
    _ephemeral_turn = {
        k: meta.get(k) for k in ("_turn_category", "_turn_roles") if meta.get(k) is not None
    }

    if not turn_policy_enabled():
        return ApplyTurnEffectsResult(
            effects=effects,
            applied=False,
            detail="turn_policy_disabled",
            plan_md=plan_before,
            run_meta=meta,
        )

    persist_turn_policy_on_run_meta(meta, effects)

    if folder is None or not folder.is_dir():
        return ApplyTurnEffectsResult(
            effects=effects,
            applied=True,
            detail="no_session_folder",
            plan_md=plan_before,
            run_meta=meta,
        )

    from agent_lab.plan.workflow import (
        emit_plan_workflow_phase_if_changed,
        init_plan_workflow_on_plan_send,
        is_plan_workflow_active,
        orchestrate_plan_workflow_pipeline,
        plan_workflow_phase,
    )
    from agent_lab.run.meta import read_run_meta

    plan_md = plan_before
    scribe_applied = False
    plan_trigger: str | None = None

    if effects.init_plan_workflow and not is_plan_workflow_active(meta):
        init_plan_workflow_on_plan_send(folder)
        meta.update(read_run_meta(folder))

    pw_force_scribe = False
    phase_before = plan_workflow_phase(meta) if is_plan_workflow_active(meta) else None

    if not skip_fsm and effects.advance_plan_workflow and not cancelled:
        plan_md, meta, pw_force_scribe = _run_fsm_tick(
            folder,
            run_meta=meta,
            plan_md=plan_md,
            plan_before=plan_before,
            synthesize=legacy_synthesize,
            cancelled=cancelled,
            on_event=on_event,
        )

    plan_md, scribe_applied, plan_trigger = _run_turn_policy_scribe(
        folder=folder,
        topic=topic,
        messages=list(messages or []),
        run_meta=meta,
        plan_before=plan_before,
        mode=mode,
        effects=effects,
        legacy_synthesize=legacy_synthesize,
        cancelled=cancelled,
        on_event=on_event,
        permissions=permissions,
        consensus_meta=consensus_meta,
        verified_result=verified_result,
        human_turn=human_turn,
        pw_force_scribe=pw_force_scribe,
    )

    if (
        not skip_peer_pipeline
        and is_plan_workflow_active(meta)
        and not cancelled
        and scribe_applied
        and active_agents
        and messages
    ):
        from agent_lab.plan.workflow import plan_workflow_should_advance_on_turn

        pw_advance = plan_workflow_should_advance_on_turn(meta, synthesize=legacy_synthesize)
        _auto_draft_advance = (
            not pw_advance
            and plan_md != plan_before
            and plan_workflow_phase(read_run_meta(folder)) == "DRAFT"
        )
        if pw_advance or _auto_draft_advance:
            plan_md, pw_replies, pw_meta = orchestrate_plan_workflow_pipeline(
                folder,
                topic=topic,
                messages=list(messages),
                plan_md=plan_md,
                plan_before=plan_before,
                synthesize=legacy_synthesize or _auto_draft_advance,
                cancelled=cancelled,
                agents=[str(a) for a in active_agents],
                permissions=permissions,
                run_meta=meta,
                on_event=on_event,
            )
            if pw_replies:
                messages.extend(pw_replies)
            if pw_meta.get("pending_approval") and on_event:
                on_event(
                    "plan_workflow_pending",
                    {"phase": plan_workflow_phase(read_run_meta(folder))},
                )

    if is_plan_workflow_active(meta):
        meta = read_run_meta(folder)
        emit_plan_workflow_phase_if_changed(
            folder,
            on_event,
            phase_before,
            plan_workflow_phase(meta),
        )

    if scribe_applied or (folder / "plan.md").is_file():
        plan_path = folder / "plan.md"
        if plan_path.is_file():
            plan_md = plan_path.read_text(encoding="utf-8")

    for key, value in _ephemeral_turn.items():
        meta.setdefault(key, value)

    return ApplyTurnEffectsResult(
        effects=effects,
        applied=True,
        detail="turn_policy_applied",
        plan_md=plan_md,
        scribe_applied=scribe_applied,
        run_meta=meta,
        plan_trigger=plan_trigger,
    )
