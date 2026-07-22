"""S1 Phase A — turn_metrics + outcome ledger unit tests (mock-only)."""

from __future__ import annotations

import json
from pathlib import Path

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
    assert metrics["failure_tags"] == []
    assert metrics["primary_tag"] is None
    assert metrics["challenge_precision"] == {}


# ---------------------------------------------------------------------------
# S1 D1 — challenge_precision (docs/S1-CHALLENGE-PRECISION.md)
# ---------------------------------------------------------------------------


def test_challenge_precision_counts_adopted_and_unadopted_by_agent() -> None:
    objections = [
        {"act": "CHALLENGE", "turn": 1, "from": "claude", "resolution": "challenger_authored_anchor"},
        {"act": "CHALLENGE", "turn": 1, "from": "codex", "status": "open"},
        {"act": "CHALLENGE", "turn": 2, "from": "claude"},  # different turn → excluded
        {"act": "AMEND", "turn": 1, "from": "claude"},  # not counted (design open question #3)
    ]
    metrics = build_turn_metrics(_TURN, objections=objections, executions=[], human_turn=1)
    cp = metrics["challenge_precision"]
    assert cp["claude"] == {"challenge_total": 1, "challenge_adopted": 1, "note_total": 0}
    assert cp["codex"] == {"challenge_total": 1, "challenge_adopted": 0, "note_total": 0}
    assert "cursor" not in cp


def test_challenge_precision_tallies_note_from_turn_acts() -> None:
    turn_acts = [
        {"agent": "claude", "act": "NOTE"},
        {"agent": "claude", "act": "NOTE"},
        {"agent": "cursor", "act": "ENDORSE"},  # not NOTE → ignored
    ]
    metrics = build_turn_metrics(
        _TURN, objections=[], executions=[], human_turn=1, turn_acts=turn_acts
    )
    cp = metrics["challenge_precision"]
    assert cp["claude"]["note_total"] == 2
    assert "cursor" not in cp  # ENDORSE alone doesn't create a row


def test_challenge_precision_defaults_empty_without_turn_acts() -> None:
    """Backward compatible: omitting turn_acts must not error, just skip NOTE tally."""
    metrics = build_turn_metrics(_TURN, objections=_OBJECTIONS, executions=[], human_turn=1)
    assert metrics["challenge_precision"] == {}  # fixture objections have no "from"


# ---------------------------------------------------------------------------
# HS1-1 — failure_tags taxonomy
# ---------------------------------------------------------------------------


def test_failure_tags_harness_infra_on_skipped_oracle() -> None:
    executions = [{"oracle": {"verdict": "skipped"}, "repair_history": []}]
    metrics = build_turn_metrics(_TURN, objections=[], executions=executions, human_turn=1)
    assert metrics["failure_tags"] == ["harness_infra"]
    assert metrics["primary_tag"] == "harness_infra"


def test_failure_tags_false_success_on_pass_without_evidence() -> None:
    executions = [{"oracle": {"verdict": "pass", "evidence": []}, "repair_history": []}]
    metrics = build_turn_metrics(_TURN, objections=[], executions=executions, human_turn=1)
    assert metrics["failure_tags"] == ["false_success"]


def test_failure_tags_absent_when_pass_has_evidence() -> None:
    executions = [{"oracle": {"verdict": "pass", "evidence": ["src/x.py:12"]}, "repair_history": []}]
    metrics = build_turn_metrics(_TURN, objections=[], executions=executions, human_turn=1)
    assert metrics["failure_tags"] == []


def test_failure_tags_weak_taste_on_unresolved_block() -> None:
    objections = [{"act": "BLOCK", "turn": 1, "status": "open"}]
    metrics = build_turn_metrics(_TURN, objections=objections, executions=[], human_turn=1)
    assert metrics["failure_tags"] == ["weak_taste"]


def test_failure_tags_weak_taste_on_repeated_challenge() -> None:
    objections = [
        {"act": "CHALLENGE", "turn": 1, "status": "open"},
        {"act": "CHALLENGE", "turn": 1, "status": "resolved_accepted"},
    ]
    metrics = build_turn_metrics(_TURN, objections=objections, executions=[], human_turn=1)
    assert metrics["failure_tags"] == ["weak_taste"]


def test_failure_tags_resolved_block_and_single_challenge_not_weak_taste() -> None:
    objections = [
        {"act": "BLOCK", "turn": 1, "status": "resolved_accepted"},
        {"act": "CHALLENGE", "turn": 1, "status": "resolved_accepted"},
    ]
    metrics = build_turn_metrics(_TURN, objections=objections, executions=[], human_turn=1)
    assert metrics["failure_tags"] == []


def test_failure_tags_primary_tag_follows_priority_order() -> None:
    # harness_infra > weak_taste > false_success — harness_infra wins even
    # though weak_taste and false_success signals are also present.
    executions = [
        {"oracle": {"verdict": "skipped"}, "repair_history": []},
        {"oracle": {"verdict": "pass", "evidence": []}, "repair_history": []},
    ]
    objections = [{"act": "BLOCK", "turn": 1, "status": "open"}]
    metrics = build_turn_metrics(_TURN, objections=objections, executions=executions, human_turn=1)
    assert set(metrics["failure_tags"]) == {"harness_infra", "weak_taste", "false_success"}
    assert metrics["primary_tag"] == "harness_infra"


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


def test_build_outcome_record_flattens_challenge_precision() -> None:
    metrics = build_turn_metrics(
        _TURN,
        objections=[{"act": "CHALLENGE", "turn": 1, "from": "claude", "resolution": "challenger_authored_anchor"}],
        executions=[],
        human_turn=1,
    )
    rec = build_outcome_record(Path("/tmp/sess-z"), "topic", metrics)
    assert rec["challenge_precision"]["claude"] == {
        "challenge_total": 1,
        "challenge_adopted": 1,
        "note_total": 0,
    }


def test_record_turn_outcome_reads_turn_acts_only_when_flag_enabled(tmp_path, monkeypatch) -> None:
    """AGENT_LAB_CHALLENGE_PRECISION gates the chat.jsonl read for NOTE tally —
    off by default (docs/S1-CHALLENGE-PRECISION.md), independent of
    TURN_METRICS/OUTCOME_LEDGER."""
    folder = tmp_path / "sess-note"
    folder.mkdir()
    run = {
        "topic": "note tally check",
        "turns": [dict(_TURN)],
        "objections": [],
        "executions": [],
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    chat_lines = [
        {"role": "user", "agent": None, "content": "topic", "ts": "t0"},
        {
            "role": "agent",
            "agent": "claude",
            "content": "note body",
            "ts": "t1",
            "envelope": {"act": "NOTE", "refs": []},
        },
    ]
    (folder / "chat.jsonl").write_text(
        "\n".join(json.dumps(line) for line in chat_lines) + "\n", encoding="utf-8"
    )

    monkeypatch.setenv("AGENT_LAB_TURN_METRICS", "1")
    monkeypatch.delenv("AGENT_LAB_CHALLENGE_PRECISION", raising=False)
    record_turn_outcome(folder, 1)
    after = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert after["turns"][-1]["turn_metrics"]["challenge_precision"] == {}

    monkeypatch.setenv("AGENT_LAB_CHALLENGE_PRECISION", "1")
    record_turn_outcome(folder, 1)
    after = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert after["turns"][-1]["turn_metrics"]["challenge_precision"]["claude"]["note_total"] == 1
