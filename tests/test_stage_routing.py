from __future__ import annotations

import pytest

from agent_lab.mode_router import resolve_active_phase
from agent_lab.turn_modes import (
    phase_default_consensus,
    stage_route_consensus,
    stage_routing_enabled,
)

# AC1: phase->route table sets ModeContract.consensus_mode (panel True / solo False),
# asserted on the resolved routing decision, not select_mode.


@pytest.mark.parametrize(
    "phase",
    ["DISCUSS", "PLAN_GATE", "PLAN_REJECT", "DRAFT", "PEER_REVIEW", "REFINE"],
)
def test_panel_phases_resolve_consensus_true(phase: str) -> None:
    assert phase_default_consensus(phase) is True
    resolved, log = stage_route_consensus(phase=phase, turn_profile=None, consensus_mode=False, stage_routing=True)
    assert resolved is True
    assert log["applied"] is True
    assert log["consensus_mode"] is True


@pytest.mark.parametrize(
    "phase",
    ["EXECUTE_QUEUE", "DRY_RUN", "MERGE_REVIEW", "VERIFY", "REPAIR"],
)
def test_solo_phases_resolve_consensus_false(phase: str) -> None:
    assert phase_default_consensus(phase) is False
    resolved, log = stage_route_consensus(phase=phase, turn_profile=None, consensus_mode=True, stage_routing=True)
    assert resolved is False
    assert log["applied"] is True
    assert log["consensus_mode"] is False


def test_phase_default_is_case_insensitive() -> None:
    assert phase_default_consensus("discuss") is True
    assert phase_default_consensus("execute_queue") is False


# AC12: CLARIFY / pre-discuss phases defer (None) so the clarity engine owns CLARIFY.


@pytest.mark.parametrize("phase", ["CLARIFY", "INTAKE", "MISSION_DEFINE", "", None, "WAT"])
def test_defer_phases_return_none(phase: str | None) -> None:
    assert phase_default_consensus(phase) is None


def test_clarify_defer_preserves_caller_consensus_mode() -> None:
    resolved_true, log_true = stage_route_consensus(
        phase="CLARIFY", turn_profile=None, consensus_mode=True, stage_routing=True
    )
    assert resolved_true is True
    assert log_true["applied"] is False
    resolved_false, log_false = stage_route_consensus(
        phase="CLARIFY", turn_profile=None, consensus_mode=False, stage_routing=True
    )
    assert resolved_false is False
    assert log_false["applied"] is False


# AC3: an explicit user turn_profile always wins (phase default not applied).


@pytest.mark.parametrize("profile", ["loop", "team", "quick", "divergence", "verified", "specialist"])
def test_explicit_profile_overrides_phase_default(profile: str) -> None:
    # EXECUTE_QUEUE would force solo, but the explicit profile keeps the caller's contract.
    resolved, log = stage_route_consensus(
        phase="EXECUTE_QUEUE", turn_profile=profile, consensus_mode=True, stage_routing=True
    )
    assert resolved is True
    assert log["explicit_profile"] is True
    assert log["applied"] is False


# AC4: the phase default applies only when there is no explicit profile.


def test_phase_default_applies_only_without_explicit_profile() -> None:
    applied_resolved, applied_log = stage_route_consensus(
        phase="DISCUSS", turn_profile=None, consensus_mode=False, stage_routing=True
    )
    assert applied_resolved is True
    assert applied_log["applied"] is True

    skipped_resolved, skipped_log = stage_route_consensus(
        phase="DISCUSS", turn_profile="loop", consensus_mode=False, stage_routing=True
    )
    assert skipped_resolved is False
    assert skipped_log["applied"] is False


def test_whitespace_only_profile_is_not_explicit() -> None:
    resolved, log = stage_route_consensus(phase="DISCUSS", turn_profile="   ", consensus_mode=False, stage_routing=True)
    assert log["explicit_profile"] is False
    assert resolved is True


# AC2: divergence is unaffected by stage routing (explicit profile short-circuits).


def test_divergence_profile_not_overridden_by_stage_routing() -> None:
    resolved, log = stage_route_consensus(
        phase="VERIFY", turn_profile="divergence", consensus_mode=False, stage_routing=True
    )
    assert log["applied"] is False
    assert resolved is False


# AC5: STAGE_ROUTING off => consensus_mode returned unchanged (per-flag OFF-parity).


@pytest.mark.parametrize(
    "phase,consensus_in",
    [
        ("DISCUSS", False),
        ("DISCUSS", True),
        ("EXECUTE_QUEUE", False),
        ("EXECUTE_QUEUE", True),
        ("CLARIFY", True),
    ],
)
def test_stage_routing_off_is_identity(phase: str, consensus_in: bool) -> None:
    resolved, log = stage_route_consensus(
        phase=phase, turn_profile=None, consensus_mode=consensus_in, stage_routing=False
    )
    assert resolved is consensus_in
    assert log["applied"] is False
    assert log["stage_routing"] is False
    assert log["phase_default"] is None


def test_stage_routing_enabled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_STAGE_ROUTING", raising=False)
    assert stage_routing_enabled() is False
    monkeypatch.setenv("AGENT_LAB_STAGE_ROUTING", "1")
    assert stage_routing_enabled() is True
    monkeypatch.setenv("AGENT_LAB_STAGE_ROUTING", "0")
    assert stage_routing_enabled() is False


def test_stage_route_consensus_default_reads_env_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_STAGE_ROUTING", raising=False)
    resolved, log = stage_route_consensus(phase="DISCUSS", turn_profile=None, consensus_mode=False)
    assert resolved is False
    assert log["applied"] is False


# Architect WATCH: the decision log carries no rounds field, so stage routing cannot
# double-count parallel/consensus rounds — it only flips the consensus_mode bool.


def test_decision_log_shape_has_no_rounds_field() -> None:
    _resolved, log = stage_route_consensus(phase="DISCUSS", turn_profile=None, consensus_mode=False, stage_routing=True)
    assert set(log.keys()) == {
        "phase",
        "stage_routing",
        "explicit_profile",
        "phase_default",
        "applied",
        "consensus_mode",
    }
    assert "rounds" not in log
    assert "parallel_rounds" not in log


# Active-phase resolution helper: plan_workflow phase takes precedence over mission_loop.


def test_resolve_active_phase_prefers_plan_workflow() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "PEER_REVIEW"},
        "mission_loop": {"enabled": True, "phase": "EXECUTE_QUEUE"},
    }
    assert resolve_active_phase(run) == "PEER_REVIEW"


def test_resolve_active_phase_falls_back_to_mission_loop() -> None:
    run = {
        "plan_workflow": {"enabled": False, "phase": "DRAFT"},
        "mission_loop": {"enabled": True, "phase": "EXECUTE_QUEUE"},
    }
    assert resolve_active_phase(run) == "EXECUTE_QUEUE"


def test_resolve_active_phase_empty_run() -> None:
    assert resolve_active_phase({}) == ""
