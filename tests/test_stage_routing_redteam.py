"""Adversarial QA / red-team for stage-aware routing (ultragoal G001).

Tries to BREAK the phase->route resolver, the active-phase resolution, the observational
telemetry, and the OFF-parity guarantee — not just confirm the happy path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_lab.mode_router import record_routing_decision, resolve_active_phase
from agent_lab.run_meta import read_run_meta
from agent_lab.turn_modes import (
    phase_default_consensus,
    stage_route_consensus,
    stage_routing_enabled,
)

_PANEL = ["DISCUSS", "PLAN_GATE", "PLAN_REJECT", "DRAFT", "PEER_REVIEW", "REFINE"]
_SOLO = ["EXECUTE_QUEUE", "DRY_RUN", "MERGE_REVIEW", "VERIFY", "REPAIR"]
_DEFER = ["CLARIFY", "INTAKE", "MISSION_DEFINE", "HUMAN_PENDING", "APPROVED", "", "GARBAGE", "  "]


# --- 1. phase_default_consensus boundary / casing / whitespace ---


def test_phase_default_casing_and_whitespace_panel() -> None:
    for phase in _PANEL:
        assert phase_default_consensus(phase) is True
        assert phase_default_consensus(phase.lower()) is True
        assert phase_default_consensus(f"  {phase}  ") is True
        assert phase_default_consensus(phase.title()) is True


def test_phase_default_casing_and_whitespace_solo() -> None:
    for phase in _SOLO:
        assert phase_default_consensus(phase) is False
        assert phase_default_consensus(phase.lower()) is False
        assert phase_default_consensus(f"\t{phase}\n") is False


def test_phase_default_defer_set_returns_none() -> None:
    for phase in _DEFER:
        assert phase_default_consensus(phase) is None
    assert phase_default_consensus(None) is None


# --- 2. stage_route_consensus adversarial invariants ---


def test_explicit_profile_on_solo_phase_keeps_caller_value() -> None:
    for profile in ["loop", "team", "quick", "divergence", "verified", "specialist", "발산"]:
        for caller in (True, False):
            resolved, log = stage_route_consensus(
                phase="EXECUTE_QUEUE",
                turn_profile=profile,
                consensus_mode=caller,
                stage_routing=True,
            )
            assert resolved is caller
            assert log["applied"] is False
            assert log["explicit_profile"] is True


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n", None])
def test_blank_profile_is_not_explicit(blank: str | None) -> None:
    resolved, log = stage_route_consensus(phase="DISCUSS", turn_profile=blank, consensus_mode=False, stage_routing=True)
    assert log["explicit_profile"] is False
    assert resolved is True
    assert log["applied"] is True


def test_off_parity_is_total_identity() -> None:
    # With stage routing OFF, the resolver is the identity on consensus_mode for EVERY phase.
    for phase in _PANEL + _SOLO + _DEFER + [None]:
        for caller in (True, False):
            for profile in (None, "loop", "team"):
                resolved, log = stage_route_consensus(
                    phase=phase,
                    turn_profile=profile,
                    consensus_mode=caller,
                    stage_routing=False,
                )
                assert resolved is caller, (phase, caller, profile)
                assert log["applied"] is False
                assert log["phase_default"] is None


def test_defer_preserves_caller_consensus_mode_both_ways() -> None:
    for phase in ["CLARIFY", "INTAKE", "MISSION_DEFINE"]:
        for caller in (True, False):
            resolved, log = stage_route_consensus(
                phase=phase, turn_profile=None, consensus_mode=caller, stage_routing=True
            )
            assert resolved is caller
            assert log["applied"] is False


def test_resolved_is_strict_bool_not_truthy() -> None:
    # consensus_mode must be a real bool, never None leaking from a defer path.
    resolved, _log = stage_route_consensus(phase="CLARIFY", turn_profile=None, consensus_mode=False, stage_routing=True)
    assert resolved is False
    assert isinstance(resolved, bool)


# --- 3. resolve_active_phase precedence + garbage tolerance ---


def test_plan_workflow_precedence_over_mission_loop() -> None:
    run = {
        "plan_workflow": {"enabled": True, "phase": "PEER_REVIEW"},
        "mission_loop": {"enabled": True, "phase": "EXECUTE_QUEUE"},
    }
    assert resolve_active_phase(run) == "PEER_REVIEW"


def test_disabled_plan_workflow_falls_back() -> None:
    run = {
        "plan_workflow": {"enabled": False, "phase": "DRAFT"},
        "mission_loop": {"enabled": True, "phase": "VERIFY"},
    }
    assert resolve_active_phase(run) == "VERIFY"


@pytest.mark.parametrize(
    "run",
    [
        {},
        {"mission_loop": None},
        {"mission_loop": {}},
        {"mission_loop": {"phase": None}},
        {"plan_workflow": None, "mission_loop": {"phase": "DISCUSS"}},
        {"mission_loop": "not-a-dict"},
    ],
)
def test_resolve_active_phase_tolerates_garbage(run: dict[str, Any]) -> None:
    out = resolve_active_phase(run)
    assert isinstance(out, str)


def test_resolve_active_phase_missing_mission_phase_is_empty() -> None:
    assert resolve_active_phase({"mission_loop": {}}) == ""
    assert resolve_active_phase({}) == ""


# --- 4. record_routing_decision: observational, no-op safe, no fan-out injection ---


def _decision(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "phase": "DISCUSS",
        "stage_routing": True,
        "explicit_profile": False,
        "phase_default": True,
        "applied": True,
        "consensus_mode": True,
    }
    base.update(over)
    return base


@pytest.mark.parametrize("folder", [None, "", 0, False])
def test_record_decision_noop_for_falsy_folder_never_raises(folder: Any) -> None:
    record_routing_decision(folder, _decision())


def test_record_decision_does_not_inject_fanout_keys(tmp_path: Path) -> None:
    (tmp_path / "run.json").write_text('{"mission_loop": {"enabled": true, "phase": "DISCUSS"}}', encoding="utf-8")
    record_routing_decision(tmp_path, _decision())
    run = read_run_meta(tmp_path)
    ml = run["mission_loop"]
    assert ml["enabled"] is True
    assert ml["phase"] == "DISCUSS"
    assert "stage_route" in ml
    # No dispatch/fan-out keys ever introduced by telemetry.
    assert "_active_consensus" not in run
    assert "agents" not in ml
    assert "consensus_mode" not in ml  # only nested under stage_route


def test_record_decision_latest_wins(tmp_path: Path) -> None:
    (tmp_path / "run.json").write_text("{}", encoding="utf-8")
    record_routing_decision(tmp_path, _decision(phase="DISCUSS", consensus_mode=True))
    record_routing_decision(tmp_path, _decision(phase="VERIFY", consensus_mode=False))
    sr = read_run_meta(tmp_path)["mission_loop"]["stage_route"]
    assert sr["phase"] == "VERIFY"
    assert sr["consensus_mode"] is False


# --- 5. flag gate honors falsy env spellings (no accidental enablement) ---


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "  ", "2", "maybe"])
def test_flag_not_enabled_for_non_true_values(val: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_STAGE_ROUTING", val)
    assert stage_routing_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "On", "Yes"])
def test_flag_enabled_for_true_values(val: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_STAGE_ROUTING", val)
    assert stage_routing_enabled() is True
