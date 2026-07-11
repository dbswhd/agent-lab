"""Mission FSM transition table — H0 contract (handlers in ``mission_lane``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.import_graph import OrchestrationLane
from agent_lab.run.state import RunStateLike

GuardKind = Literal[
    "always",
    "mission_enabled",
    "mission_define_ready",
    "mission_define_ready_pipeline",
    "clarity_met",
    "plan_gate_ok",
    "plan_gate_reject_under_cap",
    "plan_gate_reject_cap",
    "verify_pass_has_pending",
    "verify_pass_no_pending",
    "verify_fail_under_repair_cap",
    "verify_fail_repair_cap",
    "verify_fail_structural",
    "open_block",
    "discuss_recovery_pending",
    "autorun_enabled",
]


@dataclass(frozen=True, slots=True)
class RuntimeTransition:
    """One row in the orchestration transition table."""

    event: RuntimeEvent
    from_phases: frozenset[str]
    to_phase: str
    handler: str
    lane: OrchestrationLane
    guard: GuardKind = "always"
    notes: str = ""


def transition_rows_for(
    event: RuntimeEvent,
    phase: str,
) -> tuple[RuntimeTransition, ...]:
    return tuple(row for row in TRANSITION_TABLE if row.event == event and phase in row.from_phases)


# Handler-time branching guards: entry allows the event; handler picks the row outcome.
_OUTCOME_GUARDS: frozenset[GuardKind] = frozenset(
    {
        "plan_gate_ok",
        "plan_gate_reject_under_cap",
        "plan_gate_reject_cap",
        "verify_pass_has_pending",
        "verify_pass_no_pending",
        "verify_fail_under_repair_cap",
        "verify_fail_repair_cap",
        "verify_fail_structural",
    }
)


def transition_guard_satisfied(run: RunStateLike, guard: GuardKind) -> bool:
    """Evaluate a transition-table guard against current run state."""
    if guard == "always" or guard in _OUTCOME_GUARDS:
        return True

    from agent_lab.mission.loop import (
        get_mission_loop,
        mission_autorun_enabled,
        mission_define_ready,
        open_block_reason,
    )

    mission = get_mission_loop(run)

    if guard == "mission_enabled":
        return bool(mission.get("enabled"))
    if guard == "mission_define_ready":
        if not mission_define_ready(run):
            return False
        from agent_lab.mode_router import resolve_mission_bootstrap_phase

        return resolve_mission_bootstrap_phase(run) == "DISCUSS"
    if guard == "mission_define_ready_pipeline":
        if not mission_define_ready(run):
            return False
        from agent_lab.mode_router import resolve_mission_bootstrap_phase

        return resolve_mission_bootstrap_phase(run) == "CLARIFY"
    if guard == "clarity_met":
        from agent_lab.clarity import clarity_threshold_met

        return clarity_threshold_met(run)
    if guard == "discuss_recovery_pending":
        return bool((mission.get("discuss_recovery") or {}).get("pending"))
    if guard == "autorun_enabled":
        return mission_autorun_enabled(mission)
    if guard == "open_block":
        return open_block_reason(run) is None
    return False


def _applicable_rows(
    run: RunStateLike,
    event: RuntimeEvent,
    phase: str,
) -> tuple[RuntimeTransition, ...]:
    rows = transition_rows_for(event, phase)
    return tuple(row for row in rows if transition_guard_satisfied(run, row.guard))


def transition_entry_reason(
    run: RunStateLike,
    event: RuntimeEvent,
) -> tuple[bool, str, str, tuple[RuntimeTransition, ...]]:
    from agent_lab.mission.loop import get_mission_loop

    mission = get_mission_loop(run)
    phase = str(mission.get("phase") or "MISSION_DEFINE")
    enabled = bool(mission.get("enabled"))

    if event == RuntimeEvent.MISSION_ENABLE:
        applicable = _applicable_rows(run, event, phase)
        if applicable:
            return True, "mission_enable", phase, applicable
        if transition_rows_for(event, phase):
            return False, "guard_blocked", phase, ()
        return False, "invalid_transition", phase, ()

    if event == RuntimeEvent.SCRIBE_COMPLETE and not enabled:
        return True, "standalone_scribe", phase, ()

    if event in _PLAN_WORKFLOW_EVENTS:
        from agent_lab.plan.workflow_state import is_plan_workflow_active, plan_workflow_phase

        if not is_plan_workflow_active(run):
            return False, "plan_workflow_inactive", phase, ()
        pw_phase = str(plan_workflow_phase(run) or "").upper()
        if event == RuntimeEvent.PLAN_WORKFLOW_TICK:
            if pw_phase == "APPROVED":
                return False, "plan_workflow_approved", phase, ()
            return True, "plan_workflow_tick", phase, ()
        return True, "plan_workflow_advance", phase, ()

    if event in _PHASE_FREE_EVENTS:
        return True, "phase_free_event", phase, ()

    if not enabled:
        if event in STANDALONE_EVENTS:
            return True, "standalone_event", phase, ()
        return False, "mission_disabled", phase, ()

    applicable = _applicable_rows(run, event, phase)
    if applicable:
        return True, "table_edge", phase, applicable
    if transition_rows_for(event, phase):
        return False, "guard_blocked", phase, ()
    return False, "invalid_transition", phase, ()


# Wildcard: any phase listed explicitly; ``*`` means all mission phases for pause.
_W = frozenset

TRANSITION_TABLE: tuple[RuntimeTransition, ...] = (
    # --- Mission bootstrap ---
    RuntimeTransition(
        RuntimeEvent.MISSION_ENABLE,
        _W({"MISSION_DEFINE"}),
        "DISCUSS",
        "agent_lab.mission.loop:enable_mission_loop",
        OrchestrationLane.MISSION,
        guard="mission_define_ready",
        notes="Requires verified_loop or goal ready (mission_define_ready)",
    ),
    # Pipeline bootstrap: enable_mission_loop routes MISSION_DEFINE via mode_router.
    RuntimeTransition(
        RuntimeEvent.MISSION_ENABLE,
        _W({"MISSION_DEFINE"}),
        "CLARIFY",
        "agent_lab.mission.loop:enable_mission_loop",
        OrchestrationLane.MISSION,
        guard="mission_define_ready_pipeline",
        notes="Bootstrap via resolve_mission_bootstrap_phase (clarity + plan_workflow dedup)",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_PLAN_GATE,
        _W({"MISSION_DEFINE"}),
        "EXECUTE_QUEUE",
        "agent_lab.mission.loop:run_plan_gate",
        OrchestrationLane.MISSION,
        guard="plan_gate_ok",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_PLAN_GATE,
        _W({"MISSION_DEFINE"}),
        "PLAN_REJECT",
        "agent_lab.mission.loop:run_plan_gate",
        OrchestrationLane.MISSION,
        guard="plan_gate_reject_under_cap",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_CIRCUIT_BREAKER,
        _W({"MISSION_DEFINE"}),
        "MISSION_PAUSED",
        "agent_lab.mission.loop:trigger_circuit_breaker",
        OrchestrationLane.MISSION,
        guard="mission_enabled",
    ),
    # CLARIFY → DISCUSS once clarity threshold is met (maybe_advance_mission).
    RuntimeTransition(
        RuntimeEvent.MISSION_ADVANCE,
        _W({"CLARIFY"}),
        "DISCUSS",
        "agent_lab.mission.loop:maybe_advance_mission",
        OrchestrationLane.MISSION,
        guard="clarity_met",
        notes="CLARIFY clarity_threshold_met → DISCUSS; else holds (clarity_pending)",
    ),
    # --- Discuss → plan gate ---
    RuntimeTransition(
        RuntimeEvent.SCRIBE_COMPLETE,
        _W({"MISSION_DEFINE", "DISCUSS", "PLAN_GATE", "PLAN_REJECT"}),
        "PLAN_GATE",
        "agent_lab.mission.loop:after_plan_scribe",
        OrchestrationLane.MISSION,
        guard="mission_enabled",
        notes="Chains into run_plan_gate inside after_plan_scribe",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_PLAN_GATE,
        _W({"PLAN_GATE"}),
        "EXECUTE_QUEUE",
        "agent_lab.mission.loop:run_plan_gate",
        OrchestrationLane.MISSION,
        guard="plan_gate_ok",
        notes="Enqueues pending_action_indices; may autorun dry-run",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_PLAN_GATE,
        _W({"PLAN_GATE"}),
        "PLAN_REJECT",
        "agent_lab.mission.loop:run_plan_gate",
        OrchestrationLane.MISSION,
        guard="plan_gate_reject_under_cap",
        notes="Intermediate reject state before auto DISCUSS",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_PLAN_GATE,
        _W({"PLAN_REJECT"}),
        "DISCUSS",
        "agent_lab.mission.loop:run_plan_gate",
        OrchestrationLane.MISSION,
        guard="plan_gate_reject_under_cap",
        notes="Auto discuss round after Momus-lite FAIL",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_CIRCUIT_BREAKER,
        _W({"PLAN_GATE", "PLAN_REJECT"}),
        "MISSION_PAUSED",
        "agent_lab.mission.loop:trigger_circuit_breaker",
        OrchestrationLane.MISSION,
        guard="plan_gate_reject_cap",
        notes="momus_round >= max_momus_rounds",
    ),
    # --- Execute queue → dry-run → merge review ---
    RuntimeTransition(
        RuntimeEvent.EXECUTE_DRY_RUN_START,
        _W({"EXECUTE_QUEUE"}),
        "DRY_RUN",
        "agent_lab.plan.execute:run_dry_run",
        OrchestrationLane.EXECUTE,
        guard="mission_enabled",
        notes="set_execution_phase(DRY_RUN) at start of run_dry_run",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_ADVANCE,
        _W({"EXECUTE_QUEUE"}),
        "MERGE_REVIEW",
        "agent_lab.mission.loop:maybe_advance_mission",
        OrchestrationLane.MISSION,
        guard="autorun_enabled",
        notes="Via _advance_execute_queue → run_dry_run → on_dry_run_complete",
    ),
    RuntimeTransition(
        RuntimeEvent.EXECUTE_DRY_RUN_COMPLETE,
        _W({"DRY_RUN"}),
        "MERGE_REVIEW",
        "agent_lab.mission.loop:on_dry_run_complete",
        OrchestrationLane.MISSION,
        guard="mission_enabled",
    ),
    RuntimeTransition(
        RuntimeEvent.EXECUTE_DRY_RUN_CANCEL,
        _W({"DRY_RUN"}),
        "MISSION_PAUSED",
        "agent_lab.runtime.execute_lane:handle_execute_dry_run_cancel",
        OrchestrationLane.EXECUTE,
        guard="mission_enabled",
    ),
    # --- Merge review → verify or discuss ---
    RuntimeTransition(
        RuntimeEvent.EXECUTE_MERGE_APPROVED,
        _W({"MERGE_REVIEW"}),
        "VERIFY",
        "agent_lab.mission.loop:on_merge_confirm",
        OrchestrationLane.MISSION,
        guard="mission_enabled",
        notes="Oracle runs in plan_execute before on_verify_result",
    ),
    RuntimeTransition(
        RuntimeEvent.EXECUTE_MERGE_REJECTED,
        _W({"MERGE_REVIEW"}),
        "DISCUSS",
        "agent_lab.mission.loop:on_merge_abort",
        OrchestrationLane.MISSION,
        guard="mission_enabled",
    ),
    # --- Verify outcomes ---
    RuntimeTransition(
        RuntimeEvent.EXECUTE_VERIFY_PASS,
        _W({"VERIFY"}),
        "EXECUTE_QUEUE",
        "agent_lab.mission.loop:on_verify_result",
        OrchestrationLane.MISSION,
        guard="verify_pass_has_pending",
        notes="_on_verify_pass with remaining pending_action_indices",
    ),
    RuntimeTransition(
        RuntimeEvent.EXECUTE_VERIFY_PASS,
        _W({"VERIFY"}),
        "MISSION_DONE",
        "agent_lab.mission.loop:on_verify_result",
        OrchestrationLane.MISSION,
        guard="verify_pass_no_pending",
    ),
    RuntimeTransition(
        RuntimeEvent.EXECUTE_VERIFY_FAIL,
        _W({"VERIFY"}),
        "REPAIR",
        "agent_lab.mission.loop:on_verify_result",
        OrchestrationLane.MISSION,
        guard="verify_fail_under_repair_cap",
        notes="_on_verify_fail; may autorun _advance_repair",
    ),
    RuntimeTransition(
        RuntimeEvent.EXECUTE_VERIFY_FAIL,
        _W({"VERIFY"}),
        "DISCUSS",
        "agent_lab.mission.loop:on_verify_result",
        OrchestrationLane.MISSION,
        guard="verify_fail_repair_cap",
        notes="Sets discuss_recovery.pending when recoverable",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_CIRCUIT_BREAKER,
        _W({"VERIFY"}),
        "MISSION_PAUSED",
        "agent_lab.mission.loop:trigger_circuit_breaker",
        OrchestrationLane.MISSION,
        guard="verify_fail_structural",
        notes="Structural fail after repair cap",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_CIRCUIT_BREAKER,
        _W({"DISCUSS"}),
        "MISSION_PAUSED",
        "agent_lab.mission.loop:trigger_circuit_breaker",
        OrchestrationLane.MISSION,
        guard="mission_enabled",
    ),
    # --- Repair → dry-run again (same action index) ---
    RuntimeTransition(
        RuntimeEvent.MISSION_ADVANCE,
        _W({"REPAIR"}),
        "DRY_RUN",
        "agent_lab.mission.loop:maybe_advance_mission",
        OrchestrationLane.MISSION,
        guard="autorun_enabled",
        notes="Via _advance_repair → reverify_merged_execution",
    ),
    RuntimeTransition(
        RuntimeEvent.EXECUTE_REPAIR_VERIFY,
        _W({"REPAIR"}),
        "VERIFY",
        "agent_lab.mission.advance:on_merge_confirm",
        OrchestrationLane.MISSION,
        guard="mission_enabled",
        notes="Re-verify merged execution after repair",
    ),
    RuntimeTransition(
        RuntimeEvent.EXECUTE_REPAIR_COMPLETE,
        _W({"REPAIR"}),
        "MERGE_REVIEW",
        "agent_lab.runtime.execute_lane:handle_execute_repair_complete",
        OrchestrationLane.EXECUTE,
        guard="autorun_enabled",
        notes="Autorun repair advance via maybe_advance_mission",
    ),
    # --- Structural execution failure ---
    RuntimeTransition(
        RuntimeEvent.EXECUTE_STRUCTURAL_FAIL,
        _W({"DRY_RUN", "MERGE_REVIEW", "VERIFY", "REPAIR", "EXECUTE_QUEUE"}),
        "DISCUSS",
        "agent_lab.mission.loop:on_structural_execution_failure",
        OrchestrationLane.MISSION,
        guard="mission_enabled",
        notes="Also triggers circuit_breaker",
    ),
    # --- Discuss recovery (verify cap back-edge) ---
    RuntimeTransition(
        RuntimeEvent.MISSION_DISCUSS_RECOVERY,
        _W({"DISCUSS"}),
        "PLAN_GATE",
        "agent_lab.mission.loop:run_mission_discuss_recovery",
        OrchestrationLane.MISSION,
        guard="discuss_recovery_pending",
        notes="Recovery turn → scribe/plan gate re-entry",
    ),
    # --- Pause / resume / cancel ---
    RuntimeTransition(
        RuntimeEvent.MISSION_PAUSE,
        _W(
            {
                "DISCUSS",
                "PLAN_GATE",
                "PLAN_REJECT",
                "EXECUTE_QUEUE",
                "DRY_RUN",
                "MERGE_REVIEW",
                "VERIFY",
                "REPAIR",
            }
        ),
        "MISSION_PAUSED",
        "agent_lab.mission.loop:pause_mission_loop",
        OrchestrationLane.CONTROL,
        guard="mission_enabled",
    ),
    RuntimeTransition(
        RuntimeEvent.RUN_CANCEL,
        _W(
            {
                "DISCUSS",
                "PLAN_GATE",
                "PLAN_REJECT",
                "EXECUTE_QUEUE",
                "DRY_RUN",
                "MERGE_REVIEW",
                "VERIFY",
                "REPAIR",
            }
        ),
        "MISSION_PAUSED",
        "agent_lab.mission.loop:on_global_run_cancel",
        OrchestrationLane.CONTROL,
        guard="mission_enabled",
        notes="API cancel → on_global_run_cancel → pause_mission_loop",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_RESUME,
        _W({"MISSION_PAUSED"}),
        "EXECUTE_QUEUE",
        "agent_lab.mission.loop:resume_mission_loop",
        OrchestrationLane.CONTROL,
        guard="mission_enabled",
        notes="Default resume phase; also DISCUSS|PLAN_GATE|REPAIR via API body",
    ),
    RuntimeTransition(
        RuntimeEvent.MISSION_CIRCUIT_CLEAR,
        _W({"MISSION_PAUSED"}),
        "DISCUSS",
        "agent_lab.mission.loop:clear_circuit_breaker",
        OrchestrationLane.HUMAN,
        guard="mission_enabled",
        notes="Human resolves inbox; resume_phase param may target EXECUTE_QUEUE",
    ),
)

# Standalone session: these events mutate run.json but do not write mission_loop.phase.
STANDALONE_EVENTS: frozenset[RuntimeEvent] = frozenset(
    {
        RuntimeEvent.TURN_START,
        RuntimeEvent.TURN_COMPLETE,
        RuntimeEvent.TURN_PARTIAL,
        RuntimeEvent.TURN_FAILED,
        RuntimeEvent.EXECUTE_DRY_RUN_START,
        RuntimeEvent.EXECUTE_DRY_RUN_COMPLETE,
        RuntimeEvent.EXECUTE_MERGE_APPROVED,
        RuntimeEvent.EXECUTE_MERGE_REJECTED,
        RuntimeEvent.EXECUTE_VERIFY_PASS,
        RuntimeEvent.EXECUTE_VERIFY_FAIL,
        RuntimeEvent.HUMAN_INBOX_CREATED,
        RuntimeEvent.HUMAN_INBOX_RESOLVED,
        RuntimeEvent.HUMAN_BUILD_GO,
        RuntimeEvent.HUMAN_ASK,
        RuntimeEvent.GOAL_CHECK,
    }
)

_PLAN_WORKFLOW_EVENTS: frozenset[RuntimeEvent] = frozenset(
    {
        RuntimeEvent.PLAN_WORKFLOW_TICK,
        RuntimeEvent.PLAN_WORKFLOW_ADVANCE,
    }
)

_PHASE_FREE_EVENTS: frozenset[RuntimeEvent] = frozenset(
    {
        RuntimeEvent.TURN_START,
        RuntimeEvent.TURN_COMPLETE,
        RuntimeEvent.TURN_PARTIAL,
        RuntimeEvent.TURN_FAILED,
        RuntimeEvent.TURN_CANCELLED,
        RuntimeEvent.CLARIFIER_PROMPT,
        RuntimeEvent.AGENT_START,
        RuntimeEvent.AGENT_DONE,
        RuntimeEvent.CONSENSUS_ROUND,
        RuntimeEvent.SCRIBE_START,
        RuntimeEvent.HUMAN_INBOX_CREATED,
        RuntimeEvent.HUMAN_INBOX_RESOLVED,
        RuntimeEvent.HUMAN_BUILD_GO,
        RuntimeEvent.HUMAN_ASK,
        RuntimeEvent.GOAL_CHECK,
        RuntimeEvent.RUN_CANCEL,
    }
)
