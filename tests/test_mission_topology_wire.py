"""AGENT_LAB_MISSION_TOPOLOGY: arm-time topology decision wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_lab.mission.advance import on_verify_result
from agent_lab.mission.loop import enable_mission_loop
from agent_lab.mission.topology import RiskLevel, TopologyKind
from agent_lab.mission.topology_wire import (
    build_coordination_need,
    deescalate_mission_topology_after_pass,
    ensure_mission_topology,
    mission_topology_decision,
    reroute_mission_topology_after_verify,
    topology_max_agents,
    topology_skips_peer_review,
)
from agent_lab.plan.workflow import (
    get_plan_workflow,
    init_plan_workflow_on_plan_send,
    tick_plan_workflow_after_turn,
)
from agent_lab.room.dispatch import dispatch_max_fanout, parse_dispatch_from_message
from agent_lab.run.meta import patch_run_meta, read_run_meta


def _record(kind: str, max_agents: int) -> dict[str, Any]:
    return {
        "version": 1,
        "at": "2026-07-23T00:00:00Z",
        "decision": {"kind": kind, "reason": "test", "max_agents": max_agents, "fallback": "single"},
        "need": {},
        "signals": {},
    }


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    folder = tmp_path / "sess-topology"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    (folder / "topic.txt").write_text("topology test", encoding="utf-8")
    return folder


# --- need builder determinism ---


def test_build_need_critical_topic_with_clarity_components() -> None:
    run = {
        "topic": "production security migration of the payment path",
        "agents": ["cursor", "codex", "claude"],
        "mission_loop": {
            "clarity": {
                "overall": 0.2,
                "dimensions": {"goal": 0.1, "criteria": 0.1},
                "components": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
            }
        },
    }
    need, signals = build_coordination_need(run)
    assert need.risk.value == "high"
    assert need.complexity == 7
    assert need.domain_count == 3
    assert need.decomposable is True
    assert need.evaluation_clear is True
    assert need.available_specialists == 2
    assert need.manager_bottleneck is False and need.exploration is False
    assert signals["category"] == "critical"
    assert signals["clarity_available"] is True
    assert signals["component_count"] == 3
    assert signals["roster"] == ["cursor", "codex", "claude"]
    assert signals["budget_env_set"] is False


def test_build_need_bare_run_is_conservative() -> None:
    need, signals = build_coordination_need({"topic": "fix typo in readme"})
    assert need.domain_count == 1
    assert need.decomposable is False
    assert need.evaluation_clear is False
    assert need.available_specialists == 0
    assert signals["clarity_available"] is False
    assert signals["time_budget_rule"] == "category_default_v1"


# --- stamping / idempotency ---


def _ledger_topology_events(folder: Path) -> list[dict[str, Any]]:
    ledger = read_run_meta(folder).get("goal_ledger") or []
    return [e for e in ledger if e.get("event") == "mission_topology"]


def test_ensure_mission_topology_stamps_once(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    patch_run_meta(session_folder, lambda run: {**run, "topic": "fix typo"})
    record = ensure_mission_topology(session_folder)
    assert record is not None
    stored = read_run_meta(session_folder).get("mission_topology")
    assert stored is not None
    assert stored["decision"]["kind"] == str(TopologyKind.SINGLE)
    events = _ledger_topology_events(session_folder)
    assert len(events) == 1
    assert events[0]["payload"]["decision"] == stored["decision"]
    assert events[0]["payload"]["revision"] == 1
    assert events[0]["payload"]["trigger"] is None
    # second call: no rewrite, no duplicate ledger event
    assert ensure_mission_topology(session_folder) is None
    assert read_run_meta(session_folder).get("mission_topology") == stored
    assert len(_ledger_topology_events(session_folder)) == 1


def test_ensure_mission_topology_flag_off_is_noop(session_folder: Path) -> None:
    assert ensure_mission_topology(session_folder) is None
    run = json.loads((session_folder / "run.json").read_text(encoding="utf-8"))
    assert "mission_topology" not in run
    assert not _ledger_topology_events(session_folder)


def test_enable_mission_loop_arms_topology(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    enable_mission_loop(session_folder)
    stored = read_run_meta(session_folder).get("mission_topology")
    assert stored is not None and stored["version"] == 1
    # re-arm keeps the original record
    enable_mission_loop(session_folder)
    assert read_run_meta(session_folder).get("mission_topology") == stored


def test_enable_mission_loop_flag_off_no_record(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    assert read_run_meta(session_folder).get("mission_topology") is None


# --- readers ---


def test_readers_require_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    run = {"mission_topology": _record("single", 1)}
    assert mission_topology_decision(run) is None
    assert topology_max_agents(run) is None
    assert topology_skips_peer_review(run) is False
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    assert mission_topology_decision(run) == run["mission_topology"]["decision"]
    assert topology_max_agents(run) == 1
    assert topology_skips_peer_review(run) is True
    assert topology_skips_peer_review({"mission_topology": _record("peer_quorum", 3)}) is False


# --- SINGLE skips PEER_REVIEW ---


def test_peer_review_round_skipped_for_single(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    from agent_lab.plan.workflow_peer import run_plan_peer_review_round

    replies = run_plan_peer_review_round(
        Path("/nonexistent"),
        topic="t",
        messages=[],
        agents=["cursor", "codex"],
        permissions=None,
        run_meta={"mission_topology": _record("single", 1)},
        plan_md="# plan\n",
    )
    assert replies == []


def _seed_peer_review_phase(folder: Path, *, verdict: str = "iterate") -> None:
    init_plan_workflow_on_plan_send(folder)

    def _peer(run: dict[str, Any]) -> dict[str, Any]:
        pw = get_plan_workflow(run)
        pw["phase"] = "PEER_REVIEW"
        pw["peer_review_round"] = 0
        pw["last_peer_verdict"] = verdict
        run["plan_workflow"] = pw
        return run

    patch_run_meta(folder, _peer)


def test_tick_single_topology_routes_to_human_pending(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    patch_run_meta(session_folder, lambda run: {**run, "mission_topology": _record("single", 1)})
    _seed_peer_review_phase(session_folder)
    plan = "# plan\n"
    tick = tick_plan_workflow_after_turn(
        session_folder,
        synthesize=True,
        cancelled=False,
        plan_md=plan,
        plan_before=plan,
        has_pending_inbox_question=False,
    )
    assert tick.get("phase") == "HUMAN_PENDING"
    assert tick.get("pending_approval") is True
    run = read_run_meta(session_folder)
    assert (run.get("verified_loop") or {}).get("status") == "pending_approval"


def test_tick_flag_off_keeps_refine_path(session_folder: Path) -> None:
    patch_run_meta(session_folder, lambda run: {**run, "mission_topology": _record("single", 1)})
    _seed_peer_review_phase(session_folder)
    plan = "# plan\n"
    tick = tick_plan_workflow_after_turn(
        session_folder,
        synthesize=True,
        cancelled=False,
        plan_md=plan,
        plan_before=plan,
        has_pending_inbox_question=False,
    )
    assert tick.get("phase") == "REFINE"


# --- fan-out cap (lower only) ---


def test_dispatch_fanout_lower_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    assert dispatch_max_fanout({"mission_topology": _record("single", 1)}) == 1
    assert dispatch_max_fanout({"mission_topology": _record("bounded_swarm", 5)}) == 3
    assert dispatch_max_fanout({}) == 3
    assert dispatch_max_fanout() == 3
    monkeypatch.setenv("AGENT_LAB_DISPATCH_MAX_FANOUT", "2")
    assert dispatch_max_fanout({"mission_topology": _record("single", 1)}) == 1
    assert dispatch_max_fanout({"mission_topology": _record("hierarchy", 4)}) == 2


def test_dispatch_fanout_flag_off_ignores_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MISSION_TOPOLOGY", raising=False)
    assert dispatch_max_fanout({"mission_topology": _record("single", 1)}) == 3


def test_parse_dispatch_trims_to_topology_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    run_meta = {"mission_topology": _record("actor_critic", 2)}
    spec = parse_dispatch_from_message(
        "DISPATCH parallel: cursor, codex, claude: please review the module carefully",
        run_meta=run_meta,
    )
    assert spec is not None
    assert len(spec.agents) == 2
    assert spec.trimmed_agents == ("claude",)


# --- post-verify escalation-only reroute ---


def test_build_need_risk_floor_raises_and_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    need, signals = build_coordination_need({"topic": "fix typo"}, risk_floor=RiskLevel.MEDIUM)
    assert need.risk == RiskLevel.MEDIUM
    assert signals["risk_floor"] == "medium"
    need, signals = build_coordination_need({"topic": "fix typo"})
    assert signals["risk_floor"] is None


def test_build_need_risk_floor_never_lowers() -> None:
    need, _ = build_coordination_need(
        {"topic": "production security migration"}, risk_floor=RiskLevel.MEDIUM
    )
    assert need.risk == RiskLevel.HIGH


def _ledger_reroute_events(folder: Path) -> list[dict[str, Any]]:
    ledger = read_run_meta(folder).get("goal_ledger") or []
    return [e for e in ledger if e.get("event") == "mission_topology_reroute"]


def test_reroute_fail_escalates_single_to_quorum(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "topic": "production security migration of the payment path",
            "agents": ["cursor", "codex", "claude"],
            "mission_topology": _record("single", 1),
        },
    )
    result = reroute_mission_topology_after_verify(
        session_folder, verdict="fail", reason="tests red", action_index=1
    )
    assert result is not None
    assert result["kind"] == str(TopologyKind.PEER_QUORUM)
    stored = read_run_meta(session_folder)["mission_topology"]
    assert stored["revision"] == 2
    assert stored["trigger"] == "verify_fail_action_1"
    assert len(stored["history"]) == 1
    assert stored["history"][0]["decision"]["kind"] == "single"
    events = _ledger_reroute_events(session_folder)
    assert len(events) == 1
    assert events[0]["payload"]["to"]["kind"] == str(TopologyKind.PEER_QUORUM)
    assert events[0]["payload"]["from"]["kind"] == "single"
    assert events[0]["payload"]["revision"] == 2
    assert events[0]["payload"]["trigger"] == "verify_fail_action_1"


def test_reroute_structural_fail_noop(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    original = _record("single", 1)
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "topic": "production security migration",
            "mission_topology": original,
        },
    )
    result = reroute_mission_topology_after_verify(
        session_folder, verdict="fail", reason="worktree missing", action_index=1
    )
    assert result is None
    assert read_run_meta(session_folder)["mission_topology"]["decision"] == original["decision"]
    assert not _ledger_reroute_events(session_folder)


def test_reroute_pass_flag_off_missing_record_noop(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    patch_run_meta(
        session_folder,
        lambda run: {**run, "mission_topology": _record("single", 1)},
    )
    assert reroute_mission_topology_after_verify(session_folder, verdict="pass", action_index=1) is None

    monkeypatch.delenv("AGENT_LAB_MISSION_TOPOLOGY", raising=False)
    assert reroute_mission_topology_after_verify(session_folder, verdict="fail", action_index=1) is None

    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    folder2 = session_folder.parent / "no-record"
    folder2.mkdir()
    (folder2 / "run.json").write_text("{}", encoding="utf-8")
    assert reroute_mission_topology_after_verify(folder2, verdict="fail", action_index=1) is None


def test_reroute_never_downgrades(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    original = _record("peer_quorum", 3)
    patch_run_meta(
        session_folder,
        lambda run: {**run, "topic": "fix typo", "mission_topology": original},
    )
    result = reroute_mission_topology_after_verify(
        session_folder, verdict="fail", reason="tests red", action_index=1
    )
    assert result is None
    stored = read_run_meta(session_folder)["mission_topology"]
    assert stored["decision"] == original["decision"]
    assert stored.get("revision", 1) == original.get("revision", 1)


def test_reroute_repair_cap_floors_high(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "topic": "fix typo",
            "agents": ["cursor", "codex", "claude"],
            "mission_topology": _record("single", 1),
            "mission_loop": {
                "action_repair_counts": {"1": 1},
                "max_repair_per_action": 2,
            },
        },
    )
    result = reroute_mission_topology_after_verify(
        session_folder, verdict="fail", reason="tests red", action_index=1
    )
    assert result is not None
    stored = read_run_meta(session_folder)["mission_topology"]
    assert stored["need"]["risk"] == "high"
    assert stored["signals"]["risk_floor"] == "high"


def test_reroute_history_capped(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    record = _record("single", 1)
    record["history"] = [
        {"decision": _record("single", 1)["decision"], "at": "t", "revision": 1, "trigger": None}
        for _ in range(10)
    ]
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "topic": "production security migration",
            "agents": ["cursor", "codex", "claude"],
            "mission_topology": record,
        },
    )
    result = reroute_mission_topology_after_verify(
        session_folder, verdict="fail", reason="tests red", action_index=1
    )
    assert result is not None
    stored = read_run_meta(session_folder)["mission_topology"]
    assert len(stored["history"]) == 10


def test_on_verify_result_fail_triggers_reroute_phase_unchanged(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    enable_mission_loop(session_folder)

    def _verify(run: dict[str, Any]) -> dict[str, Any]:
        run["topic"] = "production security migration of the payment path"
        run["agents"] = ["cursor", "codex", "claude"]
        run["mission_topology"] = _record("single", 1)
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "VERIFY",
                "pending_action_indices": [1],
                "current_action_index": 1,
            }
        )
        return run

    patch_run_meta(session_folder, _verify)
    out = on_verify_result(session_folder, action_index=1, verdict="fail", reason="tests red")
    assert out["phase"] == "REPAIR"
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["last_verify"]["status"] == "fail"
    stored = run["mission_topology"]
    assert stored["decision"]["kind"] == str(TopologyKind.PEER_QUORUM)


def test_consumers_see_escalated_decision(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "topic": "production security migration of the payment path",
            "agents": ["cursor", "codex", "claude"],
            "mission_topology": _record("single", 1),
        },
    )
    reroute_mission_topology_after_verify(session_folder, verdict="fail", action_index=1)
    run = read_run_meta(session_folder)
    assert topology_skips_peer_review(run) is False
    assert topology_max_agents(run) == 3


# --- plateau: early-replan cap override + lightweight human escalation ---


def _seed_escalated(
    folder: Path,
    *,
    topic: str = "production security migration of the payment path",
    agents: list[str] | None = None,
    action_repair_counts: dict[str, int] | None = None,
    max_repair_per_action: int = 3,
) -> None:
    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "topic": topic,
            "agents": agents if agents is not None else ["cursor", "codex", "claude"],
            "mission_topology": _record("peer_quorum", 3),
            "mission_loop": {
                "action_repair_counts": action_repair_counts or {},
                "max_repair_per_action": max_repair_per_action,
            },
        },
    )


def test_plateau_second_fail_writes_early_replan_override(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    _seed_escalated(session_folder, action_repair_counts={"1": 1}, max_repair_per_action=3)
    result = reroute_mission_topology_after_verify(
        session_folder, verdict="fail", reason="tests red", action_index=1
    )
    assert result is None  # plateau -- no escalation happened
    ml = read_run_meta(session_folder)["mission_loop"]
    assert ml["action_repair_cap_override"]["1"] == 2


def test_plateau_first_fail_writes_no_override(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    _seed_escalated(session_folder, action_repair_counts={}, max_repair_per_action=3)
    reroute_mission_topology_after_verify(session_folder, verdict="fail", reason="tests red", action_index=1)
    ml = read_run_meta(session_folder)["mission_loop"]
    assert not ml.get("action_repair_cap_override")


def test_on_verify_fail_honors_early_replan_override(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    enable_mission_loop(session_folder)
    _seed_escalated(session_folder, action_repair_counts={"1": 1}, max_repair_per_action=3)

    def _queue(run: dict[str, Any]) -> dict[str, Any]:
        ml = run.setdefault("mission_loop", {})
        ml.update({"enabled": True, "phase": "VERIFY", "pending_action_indices": [1], "current_action_index": 1})
        return run

    patch_run_meta(session_folder, _queue)
    out = on_verify_result(session_folder, action_index=1, verdict="fail", reason="tests red")
    # without the override this would be REPAIR (count=2 < global max_rep=3);
    # the plateau-written override (2) pulls the cap in, routing to DISCUSS instead.
    assert out["phase"] == "DISCUSS"
    ml = read_run_meta(session_folder)["mission_loop"]
    assert ml["action_repair_cap_override"]["1"] == 2


def test_plateau_at_cap_flags_human_not_override(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    _seed_escalated(session_folder, action_repair_counts={"1": 1}, max_repair_per_action=2)
    reroute_mission_topology_after_verify(session_folder, verdict="fail", reason="tests red", action_index=1)
    run = read_run_meta(session_folder)
    assert not run["mission_loop"].get("action_repair_cap_override")
    items = [i for i in (run.get("human_inbox") or []) if i.get("source") == "topology_router_plateau"]
    assert len(items) == 1
    assert items[0]["action_ref"] == "1"
    assert items[0]["status"] == "pending"
    # non-blocking: no phase/circuit_breaker disruption
    assert "circuit_breaker" not in run["mission_loop"]


def test_plateau_human_flag_dedups(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    _seed_escalated(session_folder, action_repair_counts={"1": 1}, max_repair_per_action=2)
    reroute_mission_topology_after_verify(session_folder, verdict="fail", reason="tests red", action_index=1)
    reroute_mission_topology_after_verify(session_folder, verdict="fail", reason="tests red", action_index=1)
    run = read_run_meta(session_folder)
    items = [i for i in (run.get("human_inbox") or []) if i.get("source") == "topology_router_plateau"]
    assert len(items) == 1


# --- de-escalation after a clean pass streak ---


def _seed_deescalate_candidate(
    folder: Path,
    *,
    topic: str,
    agents: list[str],
    streak: int,
) -> None:
    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "topic": topic,
            "agents": agents,
            "mission_topology": _record("peer_quorum", 3),
            "mission_loop": {"consecutive_verify_passes": streak},
        },
    )


def test_deescalate_after_streak_downgrades_to_baseline(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    _seed_deescalate_candidate(session_folder, topic="fix typo", agents=["cursor"], streak=3)
    result = deescalate_mission_topology_after_pass(session_folder, action_index=1)
    assert result is not None
    assert result["kind"] == str(TopologyKind.SINGLE)
    stored = read_run_meta(session_folder)["mission_topology"]
    assert stored["revision"] == 2
    assert stored["trigger"] == "verify_pass_streak_3"
    assert len(stored["history"]) == 1
    assert stored["history"][0]["decision"]["kind"] == "peer_quorum"
    assert read_run_meta(session_folder)["mission_loop"]["consecutive_verify_passes"] == 0
    events = [e for e in (read_run_meta(session_folder).get("goal_ledger") or []) if e.get("event") == "mission_topology_deescalate"]
    assert len(events) == 1
    assert events[0]["payload"]["to"]["kind"] == str(TopologyKind.SINGLE)


def test_deescalate_below_streak_threshold_noop(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    _seed_deescalate_candidate(session_folder, topic="fix typo", agents=["cursor"], streak=2)
    assert deescalate_mission_topology_after_pass(session_folder, action_index=1) is None
    stored = read_run_meta(session_folder)["mission_topology"]
    assert stored["decision"]["kind"] == "peer_quorum"


def test_deescalate_already_single_noop(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "topic": "fix typo",
            "mission_topology": _record("single", 1),
            "mission_loop": {"consecutive_verify_passes": 5},
        },
    )
    assert deescalate_mission_topology_after_pass(session_folder, action_index=1) is None


def test_deescalate_noop_when_baseline_still_large(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    _seed_deescalate_candidate(
        session_folder,
        topic="production security migration of the payment path",
        agents=["cursor", "codex", "claude"],
        streak=3,
    )
    assert deescalate_mission_topology_after_pass(session_folder, action_index=1) is None
    stored = read_run_meta(session_folder)["mission_topology"]
    assert stored["decision"]["kind"] == "peer_quorum"


def test_deescalate_flag_off_noop(session_folder: Path) -> None:
    _seed_deescalate_candidate(session_folder, topic="fix typo", agents=["cursor"], streak=3)
    assert deescalate_mission_topology_after_pass(session_folder, action_index=1) is None


def test_fail_resets_consecutive_pass_streak(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    enable_mission_loop(session_folder)
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "topic": "fix typo",
            "agents": ["cursor"],
            "mission_loop": {
                "enabled": True,
                "phase": "EXECUTE_QUEUE",
                "pending_action_indices": [1, 2, 3],
                "current_action_index": 1,
            },
        },
    )
    on_verify_result(session_folder, action_index=1, verdict="pass")
    on_verify_result(session_folder, action_index=2, verdict="pass")
    assert read_run_meta(session_folder)["mission_loop"]["consecutive_verify_passes"] == 2
    on_verify_result(session_folder, action_index=3, verdict="fail", reason="tests red")
    assert read_run_meta(session_folder)["mission_loop"]["consecutive_verify_passes"] == 0


def test_on_verify_result_pass_streak_triggers_deescalate_e2e(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MISSION_TOPOLOGY", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    enable_mission_loop(session_folder)
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "topic": "fix typo",
            "agents": ["cursor"],
            "mission_topology": _record("peer_quorum", 3),
            "mission_loop": {
                "enabled": True,
                "phase": "EXECUTE_QUEUE",
                "pending_action_indices": [1, 2, 3],
                "current_action_index": 1,
            },
        },
    )
    on_verify_result(session_folder, action_index=1, verdict="pass")
    on_verify_result(session_folder, action_index=2, verdict="pass")
    stored = read_run_meta(session_folder)["mission_topology"]
    assert stored["decision"]["kind"] == "peer_quorum"  # streak only 2 so far
    on_verify_result(session_folder, action_index=3, verdict="pass")
    stored = read_run_meta(session_folder)["mission_topology"]
    assert stored["decision"]["kind"] == str(TopologyKind.SINGLE)
    assert read_run_meta(session_folder)["mission_loop"]["consecutive_verify_passes"] == 0
