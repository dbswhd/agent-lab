from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.mode_router import record_routing_decision
from agent_lab.run_meta import read_run_meta

# AC11: RoutingDecisionLog is observation-only. It records the stage-routing decision but
# never affects fan-out, and the room layer only calls it when STAGE_ROUTING is on, so the
# OFF path never writes (proven structurally by the `if stage_routing_enabled():` guard +
# the suite staying green with the flag default-off).


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


def test_record_routing_decision_writes_stage_route(tmp_path: Path) -> None:
    (tmp_path / "run.json").write_text("{}", encoding="utf-8")
    record_routing_decision(tmp_path, _decision())
    run = read_run_meta(tmp_path)
    stage_route = run["mission_loop"]["stage_route"]
    assert stage_route["phase"] == "DISCUSS"
    assert stage_route["consensus_mode"] is True
    assert stage_route["applied"] is True
    assert isinstance(stage_route["at"], str)
    assert stage_route["at"]


def test_record_routing_decision_noop_without_folder() -> None:
    # Observational no-op (run_room's pre-bootstrap discuss turns): must never raise.
    record_routing_decision(None, _decision())
    record_routing_decision("", _decision())


def test_record_routing_decision_is_observational_only(tmp_path: Path) -> None:
    (tmp_path / "run.json").write_text('{"mission_loop": {"enabled": true, "phase": "DISCUSS"}}', encoding="utf-8")
    record_routing_decision(tmp_path, _decision())
    run = read_run_meta(tmp_path)
    mission_loop = run["mission_loop"]
    # Existing fields preserved; only stage_route added; no dispatch flags injected.
    assert mission_loop["enabled"] is True
    assert mission_loop["phase"] == "DISCUSS"
    assert "stage_route" in mission_loop
    assert "_active_consensus" not in run
    assert "agents" not in mission_loop


def test_record_routing_decision_overwrites_latest(tmp_path: Path) -> None:
    (tmp_path / "run.json").write_text("{}", encoding="utf-8")
    record_routing_decision(tmp_path, _decision(phase="DISCUSS", consensus_mode=True))
    record_routing_decision(tmp_path, _decision(phase="VERIFY", consensus_mode=False, applied=True))
    run = read_run_meta(tmp_path)
    stage_route = run["mission_loop"]["stage_route"]
    assert stage_route["phase"] == "VERIFY"
    assert stage_route["consensus_mode"] is False
