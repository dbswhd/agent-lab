"""P0 invariant: the mission kernel is the single authority for plan gate boundaries.

``plan_workflow.phase`` may carry drafting detail the kernel does not model, but it
may never contradict the kernel-projected ``mission_loop.phase``. These tests pin that
as a build failure rather than something the reconciler repairs after the fact.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import replace

import pytest

from agent_lab.core.plan_phase_contract import (
    ALL_PLAN_PHASES,
    CANONICAL_PLAN_PHASE,
    PLAN_PHASES_BY_MISSION_PHASE,
    allowed_plan_phases,
    canonical_plan_phase,
    coerce_plan_phase,
    plan_phase_consistent,
)
from agent_lab.mission.kernel import MissionState, new_mission
from agent_lab.mission.projection import (
    _COMPATIBILITY_PHASES,
    _phase_for_mission,
    apply_mission_loop_status_projection,
)
from agent_lab.plan.workflow_state import PLAN_FSM_ORDER, apply_plan_substate_patch
from agent_lab.run.meta import read_run_meta
from agent_lab.runtime.orchestration import detect_phase_drift

#: Every (mission phase, plan phase) combination the contract must have an opinion on.
_ALL_PAIRS = list(itertools.product(sorted(PLAN_PHASES_BY_MISSION_PHASE), sorted(ALL_PLAN_PHASES)))


# --- contract completeness -------------------------------------------------


def test_contract_covers_every_mission_phase_the_projection_can_emit() -> None:
    """Every phase ``mission/projection.py`` can produce must have a contract row."""
    emitted = {_phase_for_mission(replace(new_mission("m", "goal"), state=state), None) for state in MissionState}
    missing = emitted - set(PLAN_PHASES_BY_MISSION_PHASE)
    assert missing == set(), f"mission phases without a plan-phase contract: {sorted(missing)}"


def test_contract_matches_mission_loop_compatibility_phases() -> None:
    assert set(PLAN_PHASES_BY_MISSION_PHASE) == set(_COMPATIBILITY_PHASES)


def test_contract_only_references_real_plan_phases() -> None:
    assert ALL_PLAN_PHASES == set(PLAN_FSM_ORDER)
    for mission_phase, allowed in PLAN_PHASES_BY_MISSION_PHASE.items():
        unknown = allowed - ALL_PLAN_PHASES
        assert unknown == set(), f"{mission_phase} allows unknown plan phases: {sorted(unknown)}"


def test_canonical_phase_is_itself_allowed() -> None:
    """Coercion must never produce a state that violates the contract it enforces."""
    for mission_phase, canonical in CANONICAL_PLAN_PHASE.items():
        assert plan_phase_consistent(mission_phase, canonical), (
            f"canonical plan phase {canonical} for {mission_phase} violates its own contract"
        )


def test_unknown_mission_phase_imposes_no_constraint() -> None:
    """Forward compatibility: a new mission phase must not start rejecting writes."""
    assert allowed_plan_phases("SOME_FUTURE_PHASE") is None
    assert plan_phase_consistent("SOME_FUTURE_PHASE", "APPROVED") is True
    assert allowed_plan_phases(None) is None
    assert plan_phase_consistent(None, "APPROVED") is True


# --- detector and contract agree -------------------------------------------


def test_drift_detector_agrees_with_contract() -> None:
    """``detect_phase_drift`` must be exactly the negation of the contract, for every pair."""
    for mission_phase, plan_phase in _ALL_PAIRS:
        run = {
            "plan_workflow": {"enabled": True, "phase": plan_phase},
            "mission_loop": {"enabled": True, "phase": mission_phase},
        }
        drift = detect_phase_drift(run)
        assert (drift is None) == plan_phase_consistent(mission_phase, plan_phase), (
            f"detector/contract disagree for mission={mission_phase} plan={plan_phase} (drift={drift})"
        )


# --- the load-bearing invariant --------------------------------------------


def test_write_seam_can_never_persist_drift() -> None:
    """The single plan write path cannot produce a drifting run state, for any request."""
    for mission_phase, requested in _ALL_PAIRS:
        run: dict = {
            "plan_workflow": {"enabled": True, "phase": "INTAKE"},
            "mission_loop": {"enabled": True, "phase": mission_phase},
        }
        updated = apply_plan_substate_patch(run, phase=requested)
        assert detect_phase_drift(updated) is None, (
            f"apply_plan_substate_patch(mission={mission_phase}, phase={requested}) "
            f"persisted drift: {updated['plan_workflow']['phase']}"
        )


def test_write_seam_is_transparent_when_mission_disabled() -> None:
    """Plan-only sessions (no mission loop) keep full control of their own phase."""
    for requested in sorted(ALL_PLAN_PHASES):
        run: dict = {
            "plan_workflow": {"enabled": True, "phase": "INTAKE"},
            "mission_loop": {"enabled": False},
        }
        updated = apply_plan_substate_patch(run, phase=requested)
        assert updated["plan_workflow"]["phase"] == requested
        assert "last_phase_coercion" not in updated["plan_workflow"]


def test_contradiction_is_recorded_not_swallowed() -> None:
    """A coerced write must leave evidence — silent correction is its own bug class."""
    run: dict = {
        "plan_workflow": {"enabled": True, "phase": "HUMAN_PENDING"},
        "mission_loop": {"enabled": True, "phase": "DISCUSS"},
    }
    updated = apply_plan_substate_patch(run, phase="APPROVED")
    pw = updated["plan_workflow"]
    assert pw["phase"] == "DRAFT"
    assert pw["phase_coercions"] == 1
    assert pw["last_phase_coercion"]["requested"] == "APPROVED"
    assert pw["last_phase_coercion"]["applied"] == "DRAFT"
    assert pw["last_phase_coercion"]["mission_phase"] == "DISCUSS"


def test_consistent_write_is_untouched() -> None:
    run: dict = {
        "plan_workflow": {"enabled": True, "phase": "DRAFT"},
        "mission_loop": {"enabled": True, "phase": "EXECUTE_QUEUE"},
    }
    updated = apply_plan_substate_patch(run, phase="APPROVED")
    assert updated["plan_workflow"]["phase"] == "APPROVED"
    assert "last_phase_coercion" not in updated["plan_workflow"]


def test_projection_can_be_disabled_for_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAN_PHASE_PROJECTION", "0")
    run: dict = {
        "plan_workflow": {"enabled": True, "phase": "DRAFT"},
        "mission_loop": {"enabled": True, "phase": "DISCUSS"},
    }
    updated = apply_plan_substate_patch(run, phase="APPROVED")
    assert updated["plan_workflow"]["phase"] == "APPROVED"
    assert detect_phase_drift(updated) is not None


# --- the other direction: kernel advances, plan follows ----------------------


def test_kernel_advance_drags_plan_phase_forward(tmp_path) -> None:
    """When the kernel opens the gate, a plan phase left behind is not drift — it follows."""
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "plan_workflow": {"enabled": True, "phase": "HUMAN_PENDING"},
                "mission_loop": {"enabled": True, "phase": "PLAN_GATE"},
            }
        ),
        encoding="utf-8",
    )
    approved = replace(
        new_mission(folder.name, "goal"),
        state=MissionState.READY_TO_EXECUTE,
        approved_plan_hash="abc",
    )
    apply_mission_loop_status_projection(folder, approved)

    run = read_run_meta(folder)
    assert run["mission_loop"]["phase"] == "EXECUTE_QUEUE"
    assert run["plan_workflow"]["phase"] == "APPROVED"
    assert detect_phase_drift(run) is None


def test_kernel_rewind_drags_plan_phase_back(tmp_path) -> None:
    """A revoked approval in the kernel must not leave plan_workflow claiming APPROVED."""
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "plan_workflow": {"enabled": True, "phase": "APPROVED"},
                "mission_loop": {"enabled": True, "phase": "EXECUTE_QUEUE"},
            }
        ),
        encoding="utf-8",
    )
    reopened = replace(
        new_mission(folder.name, "goal"),
        state=MissionState.AWAITING_PLAN_DECISION,
        current_plan_hash="def",
    )
    apply_mission_loop_status_projection(folder, reopened)

    run = read_run_meta(folder)
    assert run["mission_loop"]["phase"] == "PLAN_GATE"
    assert run["plan_workflow"]["phase"] == "HUMAN_PENDING"
    assert detect_phase_drift(run) is None


def test_projection_leaves_plan_only_sessions_alone(tmp_path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps(
            {
                "plan_workflow": {"enabled": True, "phase": "HUMAN_PENDING"},
                "mission_loop": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )
    apply_mission_loop_status_projection(
        folder, replace(new_mission(folder.name, "goal"), state=MissionState.READY_TO_EXECUTE)
    )
    assert read_run_meta(folder)["plan_workflow"]["phase"] == "HUMAN_PENDING"


# --- moat safety: coercion must never manufacture approval -------------------


def test_coercion_never_grants_approval_the_kernel_withheld() -> None:
    """``plan_workflow.phase == APPROVED`` may only hold where the kernel says approved.

    This is the execute-gate moat: the plan gate must not be openable by the plan FSM
    drifting into APPROVED. Coercion resolves contradictions in the kernel's favour, so
    it must never *introduce* an approval the journal does not carry.
    """
    for mission_phase, requested in _ALL_PAIRS:
        run: dict = {
            "plan_workflow": {"enabled": True, "phase": "INTAKE"},
            "mission_loop": {"enabled": True, "phase": mission_phase},
        }
        updated = apply_plan_substate_patch(run, phase=requested)
        if updated["plan_workflow"]["phase"] == "APPROVED":
            assert "APPROVED" in (allowed_plan_phases(mission_phase) or set()), (
                f"coercion produced APPROVED under mission={mission_phase}, which the kernel does not treat as approved"
            )


# --- coercion helper semantics ---------------------------------------------


def test_coerce_returns_request_when_kernel_pins_nothing() -> None:
    phase, coerced_from = coerce_plan_phase("MISSION_PAUSED", "APPROVED")
    assert phase == "APPROVED"
    assert coerced_from is None


def test_coerce_normalizes_case_and_whitespace() -> None:
    phase, coerced_from = coerce_plan_phase("execute_queue", "  approved  ")
    assert phase == "APPROVED"
    assert coerced_from is None


def test_canonical_plan_phase_unknown_is_none() -> None:
    assert canonical_plan_phase("MISSION_PAUSED") is None
    assert canonical_plan_phase("NOPE") is None
