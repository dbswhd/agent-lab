"""Kernel ↔ plan_workflow phase consistency contract (P0 — single authority).

Background
----------
``mission_loop.phase`` is a *projection* of the mission kernel
(``mission-events.jsonl`` → ``Mission.state`` → ``mission/projection.py``).
``plan_workflow.phase`` historically was an independent authority mutated by the
plan FSM (``plan/workflow_tick.py``), so the two could disagree; the disagreement
was detected after the fact (``runtime/orchestration.py::detect_phase_drift``) and
repaired by a *third* mapping (``runtime/orchestration_reconcile.py``).

This module is the single SSOT for that relationship. The kernel owns the **gate
boundaries** (pre-approval / awaiting decision / approved). ``plan_workflow.phase``
may only carry *drafting detail the kernel does not model* — CLARIFY vs DRAFT vs
PEER_REVIEW vs REFINE are all ``MissionState.DRAFTING`` — and may never contradict
the kernel.

Enforcing this at the single write seam (``plan/workflow_state.py::
apply_plan_substate_patch``) makes drift structurally unreachable instead of
repairable, which is what lets the reconciler be retired.

Dependency-zero by design (``agent_lab.core``): both ``plan`` and ``runtime`` import it.
"""

from __future__ import annotations

from typing import Final, Mapping

# plan_workflow.phase buckets, by the gate boundary they belong to.
PLAN_CLARIFY: Final[frozenset[str]] = frozenset({"INTAKE", "CLARIFY"})
PLAN_DISCUSS: Final[frozenset[str]] = frozenset({"DRAFT", "PEER_REVIEW", "REFINE"})
PLAN_GATE: Final[frozenset[str]] = frozenset({"HUMAN_PENDING"})
PLAN_DONE: Final[frozenset[str]] = frozenset({"APPROVED"})

#: Every plan_workflow phase, in FSM order.
ALL_PLAN_PHASES: Final[frozenset[str]] = PLAN_CLARIFY | PLAN_DISCUSS | PLAN_GATE | PLAN_DONE

#: Mission phases that mean "the plan is already approved and execution is underway".
EXECUTE_MISSION_PHASES: Final[frozenset[str]] = frozenset(
    {
        "EXECUTE_QUEUE",
        "DRY_RUN",
        "MERGE_REVIEW",
        "VERIFY",
        "REPAIR",
        "MISSION_DONE",
    }
)

#: The contract. ``mission_loop.phase`` → plan_workflow phases that do not contradict it.
#:
#: ``MISSION_PAUSED`` is deliberately unconstrained: a pause/circuit-breaker can be
#: entered from any mission state, so it carries no information about the plan gate.
PLAN_PHASES_BY_MISSION_PHASE: Final[Mapping[str, frozenset[str]]] = {
    "MISSION_DEFINE": PLAN_CLARIFY,
    "CLARIFY": PLAN_CLARIFY,
    "DISCUSS": PLAN_DISCUSS | PLAN_GATE,
    "PLAN_GATE": PLAN_GATE | PLAN_DISCUSS,
    "PLAN_REJECT": PLAN_DISCUSS | PLAN_GATE,
    "EXECUTE_QUEUE": PLAN_DONE,
    "DRY_RUN": PLAN_DONE,
    "MERGE_REVIEW": PLAN_DONE,
    "VERIFY": PLAN_DONE,
    "REPAIR": PLAN_DONE,
    "MISSION_DONE": PLAN_DONE,
    "MISSION_PAUSED": ALL_PLAN_PHASES,
}

#: Canonical plan phase per mission phase — used when a contradiction must be resolved
#: in the kernel's favour. Only defined where the kernel genuinely pins the plan gate.
CANONICAL_PLAN_PHASE: Final[Mapping[str, str]] = {
    "MISSION_DEFINE": "CLARIFY",
    "CLARIFY": "CLARIFY",
    "DISCUSS": "DRAFT",
    "PLAN_GATE": "HUMAN_PENDING",
    "PLAN_REJECT": "REFINE",
    "EXECUTE_QUEUE": "APPROVED",
    "DRY_RUN": "APPROVED",
    "MERGE_REVIEW": "APPROVED",
    "VERIFY": "APPROVED",
    "REPAIR": "APPROVED",
    "MISSION_DONE": "APPROVED",
}


def normalize_phase(raw: object) -> str:
    return str(raw or "").strip().upper()


def allowed_plan_phases(mission_phase: object) -> frozenset[str] | None:
    """Plan phases compatible with ``mission_phase``.

    ``None`` means "no constraint" — either the mission loop is not enabled, or the
    mission phase is unknown to this contract (forward compatibility: an unrecognised
    phase must not start rejecting writes).
    """
    phase = normalize_phase(mission_phase)
    if not phase:
        return None
    return PLAN_PHASES_BY_MISSION_PHASE.get(phase)


def plan_phase_consistent(mission_phase: object, plan_phase: object) -> bool:
    """True when ``plan_phase`` does not contradict the kernel-projected mission phase."""
    allowed = allowed_plan_phases(mission_phase)
    if allowed is None:
        return True
    return normalize_phase(plan_phase) in allowed


def canonical_plan_phase(mission_phase: object) -> str | None:
    """The plan phase the kernel implies, or ``None`` when the kernel does not pin one."""
    return CANONICAL_PLAN_PHASE.get(normalize_phase(mission_phase))


def coerce_plan_phase(
    mission_phase: object,
    requested: object,
    *,
    current: object = None,
) -> tuple[str, str | None]:
    """Project a requested plan phase onto what the kernel allows.

    Returns ``(phase, coerced_from)``. ``coerced_from`` is ``None`` when the request
    was already consistent; otherwise it is the rejected request, so callers can
    record the contradiction rather than silently swallowing it.
    """
    want = normalize_phase(requested)
    if not want:
        return normalize_phase(current), None
    if plan_phase_consistent(mission_phase, want):
        return want, None
    canonical = canonical_plan_phase(mission_phase)
    if canonical is None:
        return want, None
    return canonical, want
