"""Cross-lane import edges — orchestration triangle audit contract (F12 core)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OrchestrationLane(StrEnum):
    DISCUSS = "discuss"
    EXECUTE = "execute"
    MISSION = "mission"
    PLAN = "plan"
    RUNTIME = "runtime"
    VERIFY = "verify"
    HUMAN = "human"
    CONTEXT = "context"
    CONTROL = "control"


@dataclass(frozen=True, slots=True)
class CrossLaneImport:
    """One cross-lane import edge in the current codebase."""

    source_module: str
    target_module: str
    symbol: str
    source_lane: OrchestrationLane
    target_lane: OrchestrationLane
    note: str
    remove_in_phase: str


CROSS_LANE_IMPORTS: tuple[CrossLaneImport, ...] = (
    CrossLaneImport(
        "agent_lab.room",
        "agent_lab.runtime.runtime",
        "dispatch",
        OrchestrationLane.DISCUSS,
        OrchestrationLane.RUNTIME,
        "Scribe complete → mission plan gate via SCRIBE_COMPLETE",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.room",
        "agent_lab.runtime.invoke_execute",
        "list_plan_actions",
        OrchestrationLane.DISCUSS,
        OrchestrationLane.RUNTIME,
        "Consensus dry-run proposal action listing",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.mission.loop",
        "agent_lab.runtime.invoke_discuss",
        "continue_room_round",
        OrchestrationLane.MISSION,
        OrchestrationLane.RUNTIME,
        "Discuss recovery R1 round",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.context.bundle",
        "agent_lab.runtime.context",
        "build_mission_wisdom_block",
        OrchestrationLane.CONTEXT,
        OrchestrationLane.RUNTIME,
        "Mission notepad in agent context bundle",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.room.tasks",
        "agent_lab.runtime.invoke_execute",
        "execution_allows_task_complete",
        OrchestrationLane.DISCUSS,
        OrchestrationLane.RUNTIME,
        "Task completion gated on execution oracle",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.mission.loop",
        "agent_lab.runtime.invoke_execute",
        "run_dry_run",
        OrchestrationLane.MISSION,
        OrchestrationLane.RUNTIME,
        "Autorun dequeue → dry-run",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.mission.loop",
        "agent_lab.runtime.invoke_execute",
        "reverify_merged_execution",
        OrchestrationLane.MISSION,
        OrchestrationLane.RUNTIME,
        "Autorun REPAIR → L3 repair loop",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.mission.loop",
        "agent_lab.runtime.invoke_execute",
        "cancel_open_execution",
        OrchestrationLane.MISSION,
        OrchestrationLane.RUNTIME,
        "Pause/cancel cleanup of open execution",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.plan.execute",
        "agent_lab.runtime.runtime",
        "dispatch",
        OrchestrationLane.EXECUTE,
        OrchestrationLane.RUNTIME,
        "Execute FSM side effects",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.plan.execute",
        "agent_lab.runtime.runtime",
        "dispatch_verify_result",
        OrchestrationLane.EXECUTE,
        OrchestrationLane.RUNTIME,
        "Oracle verdict → mission FSM",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.plan.execute",
        "agent_lab.runtime.context",
        "enrich_execute_prompt",
        OrchestrationLane.EXECUTE,
        OrchestrationLane.RUNTIME,
        "Mission wisdom in execute/repair prompts",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.verified_loop",
        "agent_lab.mission.loop",
        "enable_mission_loop",
        OrchestrationLane.MISSION,
        OrchestrationLane.MISSION,
        "Verified profile approve enables mission FSM",
        "H4",
    ),
    CrossLaneImport(
        "agent_lab.plan.execute",
        "agent_lab.runtime.policy",
        "PolicyEngine",
        OrchestrationLane.EXECUTE,
        OrchestrationLane.RUNTIME,
        "pre_execute + execute objection gates",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.room",
        "agent_lab.runtime.policy",
        "PolicyEngine",
        OrchestrationLane.DISCUSS,
        OrchestrationLane.RUNTIME,
        "Agent turn gate snapshot",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.context.bundle",
        "agent_lab.runtime.policy",
        "PolicyEngine",
        OrchestrationLane.CONTEXT,
        OrchestrationLane.RUNTIME,
        "Gate block in agent constraints",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.room.tasks",
        "agent_lab.runtime.policy",
        "PolicyEngine",
        OrchestrationLane.DISCUSS,
        OrchestrationLane.RUNTIME,
        "task_completed hook policy",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.room.hooks",
        "agent_lab.runtime.policy",
        "PolicyEngine",
        OrchestrationLane.DISCUSS,
        OrchestrationLane.RUNTIME,
        "Hook ctx gate snapshot SSOT",
        "done",
    ),
    CrossLaneImport(
        "agent_lab.mission.loop",
        "agent_lab.runtime.policy",
        "PolicyEngine",
        OrchestrationLane.MISSION,
        OrchestrationLane.RUNTIME,
        "Plan gate / autorun block reason",
        "done",
    ),
)

FORBIDDEN_CROSS_IMPORTS: frozenset[tuple[str, str]] = frozenset(
    {
        ("agent_lab.plan.execute", "agent_lab.mission.loop"),
        ("agent_lab.mission.loop", "agent_lab.plan.execute"),
        ("agent_lab.room", "agent_lab.mission.loop"),
        ("agent_lab.room", "agent_lab.plan.execute"),
        ("agent_lab.mission.loop", "agent_lab.room"),
        ("agent_lab.context.bundle", "agent_lab.mission.loop"),
        ("agent_lab.room.tasks", "agent_lab.plan.execute"),
    }
)

FORBIDDEN_EXECUTE_IMPORTS = frozenset({pair for pair in FORBIDDEN_CROSS_IMPORTS if pair[0] == "agent_lab.plan.execute"})
