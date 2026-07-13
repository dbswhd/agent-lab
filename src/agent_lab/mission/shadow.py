from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from agent_lab.run.state import RunStateLike


class ShadowEventKind(StrEnum):
    PLAN_APPROVED = "plan_approved"
    PLAN_REJECTED = "plan_rejected"
    EXECUTION_MERGED = "execution_merged"
    ORACLE_PASSED = "oracle_passed"
    ORACLE_FAILED = "oracle_failed"
    MISSION_PAUSED = "mission_paused"
    STEP_COMPLETED = "step_completed"


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    kind: ShadowEventKind
    identity: str
    source: str
    detail: str


@dataclass(frozen=True, slots=True)
class OrderedParityReport:
    expected_types: tuple[str, ...]
    observed_types: tuple[str, ...]
    missing_types: tuple[str, ...]
    unexpected_types: tuple[str, ...]
    unsupported_kinds: tuple[ShadowEventKind, ...]
    ordered_match: bool
    parity: bool


_OBSERVATION_EVENT_TYPES: dict[ShadowEventKind, str | None] = {
    ShadowEventKind.PLAN_APPROVED: "PlanApproved",
    ShadowEventKind.PLAN_REJECTED: "PlanRejected",
    ShadowEventKind.EXECUTION_MERGED: "MergeCommitted",
    ShadowEventKind.ORACLE_PASSED: "OraclePassed",
    ShadowEventKind.ORACLE_FAILED: "OracleFailed",
    ShadowEventKind.MISSION_PAUSED: "BlockOpened",
    ShadowEventKind.STEP_COMPLETED: None,
}

_MISSION_EVENT_ALIASES = {
    "PlanApproved": "PlanApproved",
    "PlanRejected": "PlanRejected",
    "MergeCommitted": "MergeCommitted",
    "OraclePassed": "OraclePassed",
    "OracleFailed": "OracleFailed",
    "RepairScheduled": "OracleFailed",
    "BlockOpened": "BlockOpened",
}


def ordered_parity_report(
    observations: tuple[ShadowObservation, ...],
    observed_event_types: tuple[str, ...],
) -> OrderedParityReport:
    unsupported = tuple(
        observation.kind
        for observation in observations
        if _OBSERVATION_EVENT_TYPES[observation.kind] is None
    )
    expected = tuple(
        event_type
        for observation in observations
        if (event_type := _OBSERVATION_EVENT_TYPES[observation.kind]) is not None
    )
    target_types = frozenset(expected)
    observed = tuple(
        normalized
        for event_type in observed_event_types
        if (normalized := _MISSION_EVENT_ALIASES.get(event_type)) in target_types
    )
    remaining = list(observed)
    missing: list[str] = []
    for event_type in expected:
        try:
            remaining.remove(event_type)
        except ValueError:
            missing.append(event_type)
    ordered_match = expected == observed
    return OrderedParityReport(
        expected,
        observed,
        tuple(missing),
        tuple(remaining),
        unsupported,
        ordered_match,
        ordered_match and not missing and not remaining and not unsupported,
    )


def build_ordered_parity_report(
    before: RunStateLike,
    after: RunStateLike,
    observed_event_types: tuple[str, ...],
) -> OrderedParityReport:
    return ordered_parity_report(shadow_diff(before, after), observed_event_types)


def _mission_loop(run: RunStateLike) -> Mapping[str, Any]:
    value = run.get("mission_loop")
    return value if isinstance(value, dict) else {}


def _phase(run: RunStateLike) -> str:
    return str(_mission_loop(run).get("phase") or "")


def _plan_identity(run: RunStateLike) -> str:
    gate = _mission_loop(run).get("plan_gate")
    gate_map = gate if isinstance(gate, dict) else {}
    round_number = gate_map.get("momus_round") or _mission_loop(run).get("iteration") or 1
    return f"plan-revision-{round_number}"


def _execution_rows(run: RunStateLike) -> Mapping[str, Mapping[str, Any]]:
    rows = run.get("executions")
    if not isinstance(rows, list):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        if isinstance(row, dict):
            identity = str(row.get("id") or f"execution-{index + 1}")
            result[identity] = row
    return result


def _oracle_verdict(row: Mapping[str, Any]) -> str:
    oracle = row.get("oracle")
    if isinstance(oracle, dict):
        verdict = oracle.get("verdict")
        if verdict:
            return str(verdict).lower()
    verify = row.get("verify_after_merge")
    if isinstance(verify, dict):
        nested = verify.get("oracle")
        if isinstance(nested, dict):
            return str(nested.get("verdict") or "").lower()
    return ""


def _step_ids(run: RunStateLike) -> frozenset[str]:
    rows = run.get("completed_steps")
    if not isinstance(rows, list):
        return frozenset()
    return frozenset(str(row.get("step")) for row in rows if isinstance(row, dict) and row.get("step"))


def shadow_diff(before: RunStateLike, after: RunStateLike) -> tuple[ShadowObservation, ...]:
    observations: list[ShadowObservation] = []
    before_phase = _phase(before)
    after_phase = _phase(after)
    if after_phase == "PLAN_REJECT" and before_phase != after_phase:
        gate = _mission_loop(after).get("plan_gate")
        gate_map = gate if isinstance(gate, dict) else {}
        observations.append(
            ShadowObservation(
                ShadowEventKind.PLAN_REJECTED,
                _plan_identity(after),
                "mission_loop.plan_gate",
                str(gate_map.get("last_reject_reason") or "plan gate rejected"),
            )
        )
    before_plan = before.get("plan_workflow")
    after_plan = after.get("plan_workflow")
    before_plan_phase = str(before_plan.get("phase") or "") if isinstance(before_plan, dict) else ""
    after_plan_phase = str(after_plan.get("phase") or "") if isinstance(after_plan, dict) else ""
    if after_plan_phase == "APPROVED" and before_plan_phase != "APPROVED":
        after_plan_map = after_plan if isinstance(after_plan, dict) else {}
        observations.append(
            ShadowObservation(
                ShadowEventKind.PLAN_APPROVED,
                str(after_plan_map.get("plan_hash_at_approval") or _plan_identity(after)),
                "plan_workflow.phase",
                "plan approved",
            )
        )
    if after_phase == "MISSION_PAUSED" and before_phase != after_phase:
        observations.append(
            ShadowObservation(
                ShadowEventKind.MISSION_PAUSED,
                str(_mission_loop(after).get("last_execution_id") or "mission"),
                "mission_loop.phase",
                str(_mission_loop(after).get("pause_reason") or "mission paused"),
            )
        )
    before_rows = _execution_rows(before)
    for identity, row in _execution_rows(after).items():
        previous = before_rows.get(identity, {})
        if str(row.get("status") or "") == "merged" and str(previous.get("status") or "") != "merged":
            observations.append(ShadowObservation(ShadowEventKind.EXECUTION_MERGED, identity, "executions.status", "merged"))
        verdict = _oracle_verdict(row)
        previous_verdict = _oracle_verdict(previous)
        if verdict == "pass" and previous_verdict != "pass":
            observations.append(ShadowObservation(ShadowEventKind.ORACLE_PASSED, identity, "executions.oracle", "pass"))
        if verdict == "fail" and previous_verdict != "fail":
            detail = str((row.get("oracle") or {}).get("detail") or "oracle failed") if isinstance(row.get("oracle"), dict) else "oracle failed"
            observations.append(ShadowObservation(ShadowEventKind.ORACLE_FAILED, identity, "executions.oracle", detail))
    for step_id in sorted(_step_ids(after) - _step_ids(before)):
        observations.append(ShadowObservation(ShadowEventKind.STEP_COMPLETED, step_id, "completed_steps", "step persisted"))
    return tuple(observations)
