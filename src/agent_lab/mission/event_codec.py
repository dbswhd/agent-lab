from __future__ import annotations

from enum import StrEnum
from typing import Mapping, assert_never

from agent_lab.mission.journal import PendingEvent, StoredEvent
from agent_lab.mission.kernel import (
    BlockOpened,
    BlockResolved,
    DiffApproved,
    DiffReady,
    ExecutionGateClosed,
    ExecutionGateOpened,
    ExecutionStarted,
    MergeCommitted,
    MissionEvent,
    MissionState,
    OracleFailed,
    OraclePassed,
    PlanApproved,
    PlanOpened,
    PlanRejected,
    RepairScheduled,
)
from agent_lab.mission.messages import JsonValue


class EventCodecError(ValueError):
    pass


class EventType(StrEnum):
    PLAN_OPENED = "PlanOpened"
    PLAN_REJECTED = "PlanRejected"
    PLAN_APPROVED = "PlanApproved"
    EXECUTION_STARTED = "ExecutionStarted"
    DIFF_READY = "DiffReady"
    DIFF_APPROVED = "DiffApproved"
    MERGE_COMMITTED = "MergeCommitted"
    ORACLE_PASSED = "OraclePassed"
    ORACLE_FAILED = "OracleFailed"
    REPAIR_SCHEDULED = "RepairScheduled"
    BLOCK_OPENED = "BlockOpened"
    BLOCK_RESOLVED = "BlockResolved"
    EXECUTION_GATE_OPENED = "ExecutionGateOpened"
    EXECUTION_GATE_CLOSED = "ExecutionGateClosed"


def _text(payload: Mapping[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise EventCodecError(f"{key} must be text")
    return value


def _number(payload: Mapping[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise EventCodecError(f"{key} must be an integer")
    return value


def _flag(payload: Mapping[str, JsonValue], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise EventCodecError(f"{key} must be a boolean")
    return value


def _mission_state(payload: Mapping[str, JsonValue], key: str) -> MissionState:
    raw = _text(payload, key)
    try:
        return MissionState(raw)
    except ValueError as exc:
        raise EventCodecError(f"{key} is not a valid MissionState: {raw}") from exc


def encode_event(event: MissionEvent) -> PendingEvent:
    match event:
        case PlanOpened(plan_hash=plan_hash, revision=revision):
            return PendingEvent("PlanOpened", {"plan_hash": plan_hash, "revision": revision})
        case PlanRejected(reason=reason):
            return PendingEvent("PlanRejected", {"reason": reason})
        case PlanApproved(plan_hash=plan_hash):
            return PendingEvent("PlanApproved", {"plan_hash": plan_hash})
        case ExecutionStarted():
            return PendingEvent("ExecutionStarted", {})
        case DiffReady():
            return PendingEvent("DiffReady", {})
        case DiffApproved():
            return PendingEvent("DiffApproved", {})
        case MergeCommitted(commit_sha=commit_sha):
            return PendingEvent("MergeCommitted", {"commit_sha": commit_sha})
        case OraclePassed(detail=detail):
            return PendingEvent("OraclePassed", {"detail": detail})
        case OracleFailed(detail=detail, terminal=terminal):
            return PendingEvent("OracleFailed", {"detail": detail, "terminal": terminal})
        case RepairScheduled(attempt=attempt, detail=detail):
            return PendingEvent("RepairScheduled", {"attempt": attempt, "detail": detail})
        case BlockOpened(reason=reason):
            return PendingEvent("BlockOpened", {"reason": reason})
        case BlockResolved():
            return PendingEvent("BlockResolved", {})
        case ExecutionGateOpened(gate_id=gate_id, kind=kind, reason=reason, at_state=at_state):
            return PendingEvent(
                "ExecutionGateOpened",
                {"gate_id": gate_id, "kind": kind, "reason": reason, "at_state": at_state.value},
            )
        case ExecutionGateClosed(gate_id=gate_id):
            return PendingEvent("ExecutionGateClosed", {"gate_id": gate_id})
        case _ as unreachable:
            assert_never(unreachable)


def decode_event(event: StoredEvent) -> MissionEvent:
    payload = event.payload
    try:
        event_type = EventType(event.event_type)
    except ValueError as exc:
        raise EventCodecError(f"unknown mission event: {event.event_type}") from exc
    match event_type:
        case EventType.PLAN_OPENED:
            return PlanOpened(_text(payload, "plan_hash"), _number(payload, "revision"))
        case EventType.PLAN_REJECTED:
            return PlanRejected(_text(payload, "reason"))
        case EventType.PLAN_APPROVED:
            return PlanApproved(_text(payload, "plan_hash"))
        case EventType.EXECUTION_STARTED:
            return ExecutionStarted()
        case EventType.DIFF_READY:
            return DiffReady()
        case EventType.DIFF_APPROVED:
            return DiffApproved()
        case EventType.MERGE_COMMITTED:
            return MergeCommitted(_text(payload, "commit_sha"))
        case EventType.ORACLE_PASSED:
            return OraclePassed(_text(payload, "detail"))
        case EventType.ORACLE_FAILED:
            return OracleFailed(_text(payload, "detail"), _flag(payload, "terminal"))
        case EventType.REPAIR_SCHEDULED:
            return RepairScheduled(_number(payload, "attempt"), _text(payload, "detail"))
        case EventType.BLOCK_OPENED:
            return BlockOpened(_text(payload, "reason"))
        case EventType.BLOCK_RESOLVED:
            return BlockResolved()
        case EventType.EXECUTION_GATE_OPENED:
            return ExecutionGateOpened(
                _text(payload, "gate_id"),
                _text(payload, "kind"),
                _text(payload, "reason"),
                _mission_state(payload, "at_state"),
            )
        case EventType.EXECUTION_GATE_CLOSED:
            return ExecutionGateClosed(_text(payload, "gate_id"))
        case _ as unreachable:
            assert_never(unreachable)
