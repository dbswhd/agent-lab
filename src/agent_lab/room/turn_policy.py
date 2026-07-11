"""TurnPolicy — signal-driven Room turn side effects (Wave F).

Replaces Plan toggle / ``synthesize`` as the authority for Scribe, plan_workflow tick,
and task assign. See docs/TURN-POLICY.md.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunState, RunStateLike
from agent_lab.room.turn_contract import ContractOutcome
from agent_lab.room.turn_intent import TurnIntent
from agent_lab.room.turn_policy_models import (
    ApplyTurnEffectsResult,
    TurnEffects,
    TurnPolicyEngine,
    TurnSignals,
    ScribeTrigger,
    TurnKind as TurnKind,
    build_turn_policy_record,
)

_PLAN_DRAFT_PHASES = frozenset({"DRAFT", "REFINE"})
_PLAN_NO_SCRIBE_PHASES = frozenset({"HUMAN_PENDING", "APPROVED"})
_PLAN_FSM_TICK_PHASES = frozenset({"INTAKE", "CLARIFY", "DRAFT", "PEER_REVIEW", "REFINE"})
_TASK_ASSIGN_PHASES = frozenset({"DRAFT", "REFINE", "PEER_REVIEW"})
_SKILL_SCRIBE_INTENTS = frozenset({"plan", "plan_draft", "ralplan", "propose_build"})
_DEFAULT_PROPOSED_SKILL_INTENT_THRESHOLD = 3


def proposed_envelope_threshold() -> int:
    raw = (os.getenv("AGENT_LAB_PROPOSED_SKILL_INTENT_THRESHOLD") or "").strip()
    if not raw:
        return _DEFAULT_PROPOSED_SKILL_INTENT_THRESHOLD
    try:
        return max(1, min(32, int(raw)))
    except ValueError:
        return _DEFAULT_PROPOSED_SKILL_INTENT_THRESHOLD


def count_proposed_tags_in_turn(messages: list[Any]) -> int:
    """Count distinct ``[PROPOSED:]`` tags in the latest human turn agent replies."""
    from agent_lab.room.tasks import extract_proposed_titles

    last_user = -1
    for index, message in enumerate(messages):
        if getattr(message, "role", None) == "user":
            last_user = index
    turn = messages[last_user + 1 :] if last_user >= 0 else messages
    seen: set[str] = set()
    for message in turn:
        if getattr(message, "role", None) != "agent":
            continue
        for title in extract_proposed_titles(getattr(message, "content", "") or ""):
            seen.add(title.strip().lower())
    return len(seen)


def stamp_pending_skill_intent(folder: Path, intent: str) -> None:
    """Persist explicit plan authority for the next Room turn (slash/MCP/API)."""
    normalized = normalize_skill_intent(intent)
    if not normalized:
        return
    from agent_lab.run.meta import patch_run_meta

    def _patch(run: RunState) -> RunState:
        run["_pending_skill_intent"] = normalized
        return run

    patch_run_meta(folder, _patch)


def normalize_skill_intent(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip().lower()
    return text or None


def skill_intent_opens_scribe(intent: str | None) -> bool:
    return normalize_skill_intent(intent) in _SKILL_SCRIBE_INTENTS


def pop_pending_skill_intent(folder: Path | None, run_meta: RunStateLike) -> str | None:
    """Consume slash/API pending intent; clear from memory and disk."""
    intent = normalize_skill_intent(run_meta.get("_pending_skill_intent"))
    if not intent:
        return None
    from agent_lab.run.meta import patch_run_meta, stamp_run_meta

    run_meta.pop("_pending_skill_intent", None)
    stamp_run_meta(run_meta, _pending_skill_intent=None)
    if folder is not None and folder.is_dir():

        def _clear(run: RunState) -> RunState:
            run.pop("_pending_skill_intent", None)
            return run

        patch_run_meta(folder, _clear)
    return intent


def stamp_active_skill_intent(run_meta: RunStateLike, intent: str | None) -> None:
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, _active_skill_intent=normalize_skill_intent(intent))


def turn_policy_enabled() -> bool:
    """``AGENT_LAB_TURN_POLICY=1`` — default on (Wave F4). Set ``0`` for legacy path."""
    raw = (os.getenv("AGENT_LAB_TURN_POLICY") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def detect_plan_execute_intent(text: str) -> bool:
    """Topic asks for plan → approve → execute → verify (not casual discuss)."""
    from agent_lab.room.turn_intent import is_execute_lane_topic

    return is_execute_lane_topic(text)


def resolve_discuss_light(
    *,
    mode: str,
    synthesize: bool,
    consensus_mode: bool,
    agent_rounds: int,
    room_preset: str | None,
    turn_profile: str | None,
    topic: str,
    run_meta: RunStateLike | None = None,
) -> bool:
    """§3.2.1 light discuss — off for plan/execute workflow topics and active plan FSM."""
    from agent_lab.plan.workflow import is_plan_workflow_active

    meta = run_meta or {}
    if is_plan_workflow_active(meta):
        return False
    session_topic = str(meta.get("topic") or "").strip()
    current_topic = (topic or "").strip()
    if _plan_execute_intent(current_topic, session_topic):
        return False
    preset = (room_preset or "").strip().lower()
    profile = (turn_profile or "").strip().lower()
    return bool(
        (mode or "discuss").strip().lower() == "discuss"
        and not synthesize
        and not consensus_mode
        and agent_rounds <= 1
        and (preset == "supervisor" or profile == "loop")
    )


def maybe_stamp_plan_execute_skill_intent(run: RunState, *, topic: str) -> None:
    """Auto plan authority for execute-lane dogfood topics (TurnPolicy era — no Plan toggle)."""
    if not turn_policy_enabled():
        return
    session_topic = str(run.get("topic") or "").strip()
    if not _plan_execute_intent(topic, session_topic):
        return
    if normalize_skill_intent(run.get("_pending_skill_intent")) or normalize_skill_intent(
        run.get("_active_skill_intent"),
    ):
        return
    run["_pending_skill_intent"] = "plan"


def _route_category_for_topic(topic: str, run_meta: RunStateLike) -> str | None:
    """Lightweight topic route — used before full turn_routing when TurnPolicy boots."""
    text = (topic or "").strip()
    if not text:
        return None
    from agent_lab.topic_router import resolve_topic_route

    route = resolve_topic_route(
        text,
        turn_profile=str(run_meta.get("turn_profile") or ""),
        session_template=str(run_meta.get("session_template") or ""),
    )
    return str(route.category or "") or None


def _route_category_from_run_meta(run_meta: RunStateLike) -> str | None:
    cat = run_meta.get("_turn_category")
    if isinstance(cat, dict):
        value = str(cat.get("value") or "").strip().lower()
        if value:
            return value
    return None


def skip_plan_fsm_bootstrap(signals: TurnSignals) -> bool:
    """Casual discuss / anchored quick tasks must not boot plan FSM (P0-3)."""
    if signals.skill_intent or signals.proposed_tags_count > 0:
        return False
    if signals.plan_execute_intent:
        return False
    clarity_skip = signals.clarity_short_circuit and not signals.plan_execute_intent
    return bool(signals.route_category == "quick" or signals.discuss_light or clarity_skip)


def _preset_norm(signals: TurnSignals) -> str:
    return (signals.room_preset or "").strip().lower()


def is_fast_turn(signals: TurnSignals) -> bool:
    """Low-side-effect path — single-agent quick, no FSM/scribe (TurnContract §8.2 P2).

    ``room_preset`` no longer short-circuits this to False: the Composer sends an
    implicit constant preset for every turn now (``IMPLICIT_ROOM_PRESET``), so an
    unconditional "supervisor preset -> never fast" branch would permanently kill
    the quick/anchored fast path for every real session. Only the explicit
    ``preset == "fast"`` override is preset-driven; everything else routes on the
    same category/clarity/roster signals ``skip_plan_fsm_bootstrap`` already uses.
    """
    if signals.plan_execute_intent:
        return False
    preset = _preset_norm(signals)
    if preset == "fast":
        return True
    if signals.skill_intent or signals.proposed_tags_count > 0:
        return False
    if signals.roster_size > 1:
        return False
    if signals.clarity_short_circuit:
        return True
    return signals.route_category == "quick" and signals.roster_size <= 1


def is_supervisor_turn(signals: TurnSignals) -> bool:
    """Plan FSM / multi-agent dogfood path (TurnContract §8.2 P2)."""
    if is_fast_turn(signals):
        return False
    return _preset_norm(signals) != "fast"


def supervisor_turn_from_run_meta(run_meta: RunStateLike | None) -> bool | None:
    """Read the TurnPolicy-stamped per-turn ``routing_contract.supervisor_turn`` signal.

    ``prepare_turn_policy_before_agent_round`` stamps this onto the run_meta ``turn_policy``
    field before any per-turn routing/role logic runs (see ``turn_flow_phases.prepare_turn_routing_phase``
    → ``run_consensus_phase``). Callers gating pre-turn, fast-turn-sensitive work (role
    overrides, history-based advisors) should prefer this over a raw ``room_preset``
    check — the Composer sends a constant implicit "supervisor" preset on every turn
    now (TurnContract §8.2 P2), so the raw preset no longer distinguishes fast/quick
    turns from genuine supervisor ones. Returns ``None`` when the stamp is absent
    (turn_policy disabled, or run_meta built outside the normal turn pipeline, e.g. in
    tests) so callers can fall back to their own legacy default.
    """
    if not isinstance(run_meta, dict):
        return None
    turn_policy = run_meta.get("turn_policy")
    if not isinstance(turn_policy, dict):
        return None
    routing_contract = turn_policy.get("routing_contract")
    if not isinstance(routing_contract, dict) or "supervisor_turn" not in routing_contract:
        return None
    return bool(routing_contract["supervisor_turn"])


def is_supervisor_turn_with_preset_fallback(
    run_meta: RunStateLike | None,
    *,
    room_preset: str = "",
) -> bool:
    """Prefer TurnPolicy-stamped signal; fall back to raw ``room_preset`` when absent."""
    signal = supervisor_turn_from_run_meta(run_meta)
    if signal is not None:
        return signal
    return room_preset.strip().lower() == "supervisor"


def _plan_execute_intent(current_topic: str, session_topic: str) -> bool:
    if detect_plan_execute_intent((current_topic or "").strip()):
        return True
    session = (session_topic or "").strip()
    return bool(session) and detect_plan_execute_intent(session)




def _contract_history_from_outcome_rows() -> list[ContractOutcome]:
    from agent_lab.outcome_harvester import load_outcome_rows

    history: list[ContractOutcome] = []
    for row in load_outcome_rows():
        contract_id = row.get("contract_id")
        if not isinstance(contract_id, str) or not contract_id:
            continue
        verdict = row.get("final_verdict")
        execute_intent = row.get("execute_intent")
        try:
            repair_attempts = max(0, int(row.get("repair_attempts") or 0))
        except (TypeError, ValueError):
            continue
        history.append(
            {
                "contract_id": contract_id,
                "phase": str(row.get("phase") or "") or None,
                "final_verdict": verdict if isinstance(verdict, str) else None,
                "repair_attempts": repair_attempts,
                "escalated": bool(row.get("escalated")),
                "task_kind": str(row.get("task_kind") or "") or None,
                "risk": str(row.get("risk") or "") or None,
                "execute_intent": execute_intent if isinstance(execute_intent, bool) else None,
            },
        )
    return history


def _stamp_turn_contract_on_run_meta(
    run_meta: RunState,
    *,
    topic: str,
    history: list[ContractOutcome],
    intent: TurnIntent | None = None,
) -> None:
    from agent_lab.room.turn_contract import (
        build_turn_contract,
        contract_runtime_controls,
        contract_runtime_applied,
        observe_turn,
        turn_contract_mode,
    )
    from agent_lab.run.meta import stamp_run_meta

    mode = turn_contract_mode()
    if mode == "off":
        run_meta.pop("turn_contract", None)
        return
    turn_contract = build_turn_contract(intent or observe_turn(topic, run_meta), history=history).to_snapshot()
    controls = contract_runtime_controls(str(turn_contract["contract_id"]))
    applied = contract_runtime_applied(mode, turn_contract)
    turn_contract["rollout_mode"] = mode
    turn_contract["applied"] = applied
    turn_contract["runtime_controls"] = {
        "agent_limit": controls.agent_limit,
        "max_rounds": controls.max_rounds,
        "consensus": controls.consensus,
    }
    stamp_run_meta(run_meta, turn_contract=turn_contract)


def prepare_turn_policy_before_agent_round(
    folder: Path,
    run_meta: RunState,
    *,
    human_turn: int,
    topic: str = "",
) -> tuple[RunState, TurnEffects | None]:
    """Resolve and persist TurnEffects before agent round; bootstrap FSM when needed."""
    if not turn_policy_enabled():
        return run_meta, None
    from agent_lab.plan.workflow import (
        init_plan_workflow_on_plan_send,
        is_plan_workflow_active,
    )
    from agent_lab.run.meta import read_run_meta
    from agent_lab.room.turn_contract import turn_contract_mode

    skill_hint = normalize_skill_intent(run_meta.get("_active_skill_intent"))
    signals = TurnSignals.from_run_meta(
        run_meta,
        topic=topic or None,
        supervisor_first_turn=human_turn <= 1,
        skill_intent=skill_hint,
    )
    room_preset_hint = signals.room_preset
    effects = TurnPolicyEngine.resolve(signals)
    persist_turn_policy_on_run_meta(run_meta, effects, signals=signals)
    mode = turn_contract_mode()
    history = _contract_history_from_outcome_rows() if mode != "off" else []
    _stamp_turn_contract_on_run_meta(run_meta, topic=topic, history=history, intent=signals.intent)
    if folder.is_dir() and effects.init_plan_workflow and not is_plan_workflow_active(run_meta):
        init_plan_workflow_on_plan_send(folder)
        run_meta = read_run_meta(folder)
        signals = TurnSignals.from_run_meta(
            run_meta,
            topic=topic or None,
            room_preset=room_preset_hint,
            supervisor_first_turn=human_turn <= 1,
            skill_intent=skill_hint,
        )
        effects = TurnPolicyEngine.resolve(signals)
        persist_turn_policy_on_run_meta(run_meta, effects, signals=signals)
        _stamp_turn_contract_on_run_meta(run_meta, topic=topic, history=history, intent=signals.intent)
    snap_tp = run_meta.get("turn_policy")
    snap_tk = run_meta.get("turn_kind")
    snap_tc = run_meta.get("turn_contract")
    snap_rp = run_meta.get("room_preset") or room_preset_hint
    if folder.is_dir() and (isinstance(snap_tp, dict) or snap_tk or snap_rp):
        from agent_lab.run.meta import patch_run_meta

        def _persist(run: RunState) -> RunState:
            if isinstance(snap_tp, dict):
                run["turn_policy"] = snap_tp
            if snap_tk:
                run["turn_kind"] = snap_tk
            if snap_rp:
                run["room_preset"] = snap_rp
            if mode == "off":
                run.pop("turn_contract", None)
            elif isinstance(snap_tc, dict):
                run["turn_contract"] = snap_tc
            return run

        patch_run_meta(folder, _persist)
    return run_meta, effects


def should_assign_tasks_for_run_meta(run_meta: RunStateLike | None) -> bool:
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


def is_discuss_only_for_run_meta(run_meta: RunStateLike | None) -> bool:
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


def persist_turn_policy_on_run_meta(
    run_meta: RunStateLike,
    effects: TurnEffects,
    *,
    signals: TurnSignals | None = None,
) -> None:
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(
        run_meta,
        turn_policy=build_turn_policy_record(effects, signals),
        turn_kind=effects.turn_kind,
    )


def assign_task_owners_from_run_meta(run_meta: RunStateLike | None) -> bool | None:
    """Read persisted ``turn_policy.assign_task_owners`` snapshot; None if absent."""
    tp = (run_meta or {}).get("turn_policy")
    if isinstance(tp, dict) and "assign_task_owners" in tp:
        return bool(tp.get("assign_task_owners"))
    return None


def _scribe_idempotency_key(human_turn: int, trigger: ScribeTrigger) -> str:
    return f"{human_turn}:{trigger}"


def _already_scribed(run_meta: RunStateLike, key: str) -> bool:
    applied = run_meta.get("_turn_policy_scribe_keys") or []
    if not isinstance(applied, list):
        return False
    return key in applied


def _mark_scribed(run_meta: RunStateLike, key: str) -> None:
    applied = list(run_meta.get("_turn_policy_scribe_keys") or [])
    if key not in applied:
        applied.append(key)
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, _turn_policy_scribe_keys=applied)


def _plan_trigger_for_scribe(trigger: ScribeTrigger) -> str:
    if trigger == "plan_workflow_draft":
        return "auto_turn"
    if trigger == "skill_intent":
        return "plan_turn"
    if trigger in ("consensus_reached", "verified_loop_done", "synthesize_only"):
        return trigger
    return "auto_turn"


def _run_fsm_tick(
    folder: Path,
    *,
    run_meta: RunState,
    plan_md: str,
    plan_before: str,
    synthesize: bool,
    cancelled: bool,
    on_event: Any,
) -> tuple[str, RunState, bool]:
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
    run_meta: RunStateLike,
    plan_before: str,
    mode: str,
    effects: TurnEffects,
    cancelled: bool,
    on_event: Any,
    permissions: dict[str, Any] | None,
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
    plan_trigger = _plan_trigger_for_scribe(trigger)

    if trigger == "consensus_reached":
        auto = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta=consensus_meta,
            synthesize=False,
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
            user_plan_send=False,
            cancelled=cancelled,
            on_event=on_event,
            session_folder=folder,
            plan_trigger=plan_trigger,
        )
        scribe_applied = bool(plan_md and plan_md != plan_before) or trigger in (
            "plan_workflow_draft",
            "skill_intent",
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
    run_meta: RunStateLike | None = None,
    plan_before: str = "",
    mode: str = "discuss",
    cancelled: bool = False,
    active_agents: list[Any] | None = None,
    permissions: dict[str, Any] | None = None,
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
    if isinstance(run_meta, RunState):
        meta = run_meta
    elif run_meta:
        meta = RunState.from_memory(run_meta)
    else:
        meta = RunState.empty()
    _ephemeral_turn = {k: meta.get(k) for k in ("_turn_category", "_turn_roles") if meta.get(k) is not None}

    if not turn_policy_enabled():
        return ApplyTurnEffectsResult(
            effects=effects,
            applied=False,
            detail="turn_policy_disabled",
            plan_md=plan_before,
            run_meta=meta,
        )

    persist_turn_policy_on_run_meta(meta, effects, signals=signals)

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
            synthesize=False,
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
        pw_advance = bool(effects.advance_plan_workflow)
        _auto_draft_advance = (
            not pw_advance and plan_md != plan_before and plan_workflow_phase(read_run_meta(folder)) == "DRAFT"
        )
        if pw_advance or _auto_draft_advance:
            plan_md, pw_replies, pw_meta = orchestrate_plan_workflow_pipeline(
                folder,
                topic=topic,
                messages=list(messages),
                plan_md=plan_md,
                plan_before=plan_before,
                synthesize=_auto_draft_advance,
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
