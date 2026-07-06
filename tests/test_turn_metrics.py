"""S1 Phase A — turn_metrics + outcome ledger unit tests (mock-only)."""

from __future__ import annotations

import json

from agent_lab.outcome_harvester import (
    append_outcome,
    build_outcome_record,
    outcomes_path,
    record_turn_outcome,
)
from agent_lab.turn_metrics import build_turn_metrics

_TURN = {
    "synthesize": True,
    "agents": ["cursor", "codex", "claude"],
    "agent_parallel_rounds": 3,
    "latency_ms": 311418,
    "consensus": {"status": "reached"},
    "category": {"value": "standard", "source": "heuristic"},
    "roles": {"cursor": "proposer", "codex": "executor", "claude": "critic"},
}

_OBJECTIONS = [
    {"act": "CHALLENGE", "turn": 1, "status": "resolved_accepted"},
    {"act": "CHALLENGE", "turn": 1, "status": "open"},
    {"act": "AMEND", "turn": 1},
    {"act": "BLOCK", "turn": 2},  # different turn → excluded
]

_EXECUTIONS = [
    {"oracle": {"verdict": "pass"}, "repair_history": []},
    {"verify_after_merge": {"status": "failed"}, "repair_history": [{"attempt": 1}]},
]


def test_build_turn_metrics_rolls_up_signals() -> None:
    metrics = build_turn_metrics(_TURN, objections=_OBJECTIONS, executions=_EXECUTIONS, human_turn=1)
    assert metrics["schema_version"] == 1
    assert metrics["category"] == "standard"
    assert metrics["route_source"] == "heuristic"
    assert metrics["roles"]["codex"] == "executor"
    assert metrics["rounds_used"] == 3
    assert metrics["consensus_reached"] is True
    assert metrics["synthesized"] is True
    # objections filtered to human_turn=1
    assert metrics["objection_summary"] == {"CHALLENGE": 2, "AMEND": 1}
    assert metrics["objection_resolution"] == {
        "CHALLENGE": {"accepted": 1, "wontfix": 0, "open": 1},
    }
    roll = metrics["oracle_rollup"]
    assert roll["verify_pass"] == 1
    assert roll["verify_fail"] == 1
    assert roll["repair_attempts"] == 1
    assert roll["final_verdict"] == "fail"  # last execution wins
    assert metrics["advisor_rationale"] is None


def test_build_turn_metrics_empty_inputs() -> None:
    metrics = build_turn_metrics({}, objections=[], executions=[], human_turn=1)
    assert metrics["category"] == ""
    assert metrics["objection_summary"] == {}
    assert metrics["objection_resolution"] == {}
    assert metrics["oracle_rollup"]["final_verdict"] is None


def test_append_and_record_outcome(tmp_path, monkeypatch) -> None:
    folder = tmp_path / "sess-x"
    folder.mkdir()
    run = {
        "topic": "pipeline preset verify",
        "turns": [dict(_TURN)],
        "objections": _OBJECTIONS,
        "executions": _EXECUTIONS,
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")

    root = tmp_path / "root"
    root.mkdir()

    # direct ledger write
    rec = build_outcome_record(
        folder,
        "pipeline preset verify",
        build_turn_metrics(_TURN, objections=_OBJECTIONS, executions=_EXECUTIONS, human_turn=1),
    )
    assert rec["v"] == 1
    assert "pipeline" in rec["topic_terms"]
    assert rec["topic_hash"].startswith("sha1:")
    assert rec["objection_resolution"] == {
        "CHALLENGE": {"accepted": 1, "wontfix": 0, "open": 1},
    }
    append_outcome(rec, root=root)
    assert outcomes_path(root).read_text(encoding="utf-8").count("\n") == 1


def test_record_turn_outcome_flag_gated(tmp_path, monkeypatch) -> None:
    folder = tmp_path / "sess-y"
    folder.mkdir()
    run = {"topic": "x topic", "turns": [dict(_TURN)], "objections": [], "executions": []}
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")

    monkeypatch.delenv("AGENT_LAB_TURN_METRICS", raising=False)
    monkeypatch.delenv("AGENT_LAB_OUTCOME_LEDGER", raising=False)
    # both off → no mutation
    record_turn_outcome(folder, 1)
    after = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert "turn_metrics" not in after["turns"][-1]

    monkeypatch.setenv("AGENT_LAB_TURN_METRICS", "1")
    record_turn_outcome(folder, 1)
    after = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert after["turns"][-1]["turn_metrics"]["category"] == "standard"
