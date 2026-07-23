"""AGENT_LAB_MISSION_TOPOLOGY: arm-time topology decision wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_lab.mission.loop import enable_mission_loop
from agent_lab.mission.topology import TopologyKind
from agent_lab.mission.topology_wire import (
    build_coordination_need,
    ensure_mission_topology,
    mission_topology_decision,
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
    assert len(_ledger_topology_events(session_folder)) == 1
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
