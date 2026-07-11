"""Runtime event catalog — single vocabulary for orchestration dispatch."""

from __future__ import annotations

from enum import StrEnum


class RuntimeEvent(StrEnum):
    """Events that may change session phase or orchestration state."""

    # --- Discuss lane (room.py) ---
    TURN_START = "turn.start"
    TURN_COMPLETE = "turn.complete"
    TURN_PARTIAL = "turn.partial"
    TURN_FAILED = "turn.failed"
    TURN_CANCELLED = "turn.cancelled"
    CLARIFIER_PROMPT = "clarifier.prompt"
    AGENT_START = "agent.start"
    AGENT_DONE = "agent.done"
    CONSENSUS_ROUND = "consensus.round"
    SCRIBE_START = "scribe.start"
    SCRIBE_COMPLETE = "scribe.complete"
    GOAL_CHECK = "goal.check"

    # --- Plan workflow FSM (plan/workflow_tick.py) ---
    PLAN_WORKFLOW_TICK = "plan.workflow.tick"
    PLAN_WORKFLOW_ADVANCE = "plan.workflow.advance"

    # --- Execute lane (plan_execute.py) ---
    EXECUTE_DRY_RUN_START = "execute.dry_run.start"
    EXECUTE_DRY_RUN_COMPLETE = "execute.dry_run.complete"
    EXECUTE_DRY_RUN_CANCEL = "execute.dry_run.cancel"
    EXECUTE_MERGE_APPROVED = "execute.merge.approved"
    EXECUTE_MERGE_REJECTED = "execute.merge.rejected"
    EXECUTE_VERIFY_PASS = "execute.verify.pass"
    EXECUTE_VERIFY_FAIL = "execute.verify.fail"
    EXECUTE_REPAIR_START = "execute.repair.start"
    EXECUTE_REPAIR_COMPLETE = "execute.repair.complete"
    EXECUTE_REPAIR_VERIFY = "execute.repair.verify"
    EXECUTE_STRUCTURAL_FAIL = "execute.structural.fail"

    # --- Mission conductor (mission_loop.py) ---
    MISSION_ENABLE = "mission.enable"
    MISSION_PLAN_GATE = "mission.plan_gate"
    MISSION_ADVANCE = "mission.advance"
    MISSION_PAUSE = "mission.pause"
    MISSION_RESUME = "mission.resume"
    MISSION_CIRCUIT_BREAKER = "mission.circuit_breaker"
    MISSION_CIRCUIT_CLEAR = "mission.circuit_breaker.clear"
    MISSION_DISCUSS_RECOVERY = "mission.discuss_recovery"

    # --- Human lane (human_inbox.py, execute MCP) ---
    HUMAN_INBOX_CREATED = "human.inbox.created"
    HUMAN_INBOX_RESOLVED = "human.inbox.resolved"
    HUMAN_BUILD_GO = "human.build_go"
    HUMAN_ASK = "human.ask"

    # --- Run control ---
    RUN_CANCEL = "run.cancel"
