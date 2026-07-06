"""S1 Phase A — execute-completion outcome row (mock-only).

Regression guard for the 2026-07 diagnosis: ``record_turn_outcome`` only
fires when a Room turn closes and rolls up whatever ``executions`` exist in
run.json *at that moment*. In the normal flow (discuss/plan turn -> execute ->
session ends, no follow-up chat turn) the Oracle verdict is decided *after*
the last recorded turn's ledger row, so every row in the real ``.agent-lab/outcomes.jsonl``
carried ``final_verdict: null`` and the S1 lift signal (§1.4 KPI) was always
zero. ``record_execute_outcome`` closes that gap by writing a row at the
point execute/verify actually knows the verdict.
"""

from __future__ import annotations

import json

from agent_lab.outcome_harvester import outcomes_path, record_execute_outcome, record_turn_outcome

_TURN = {
    "agents": ["cursor", "codex", "claude"],
    "agent_parallel_rounds": 1,
    "consensus": {"status": "reached"},
    "category": {"value": "standard", "source": "heuristic"},
    "roles": {"cursor": "proposer", "codex": "executor", "claude": "critic"},
}


def _write_run(folder, *, executions=None) -> None:
    folder.mkdir()
    run = {
        "topic": "JWT path in src/auth.py — pick retry strategy.",
        "turns": [dict(_TURN)],
        "objections": [],
        "executions": executions or [],
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")


def test_record_execute_outcome_writes_verdict_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))

    folder = tmp_path / "sess-exec"
    _write_run(folder)

    execution = {
        "id": "exec-1",
        "action_key": "auth-retry",
        "oracle": {"verdict": "pass"},
        "repair_history": [],
    }
    record_execute_outcome(folder, execution)

    rows = [json.loads(line) for line in outcomes_path().read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["phase"] == "execute"
    assert row["final_verdict"] == "pass"
    assert row["execution_id"] == "exec-1"
    assert row["repair_attempts"] == 0
    # episode-key context (S2) borrowed from the last Room turn
    assert row["category"] == "standard"
    assert row["roles"]["codex"] == "executor"
    assert row["agents"] == ["cursor", "codex", "claude"]


def test_record_execute_outcome_falls_back_to_verify_after_merge_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))

    folder = tmp_path / "sess-exec2"
    _write_run(folder)

    execution = {
        "id": "exec-2",
        "verify_after_merge": {"status": "failed"},
        "repair_history": [{"attempt": 1}, {"attempt": 2}],
    }
    record_execute_outcome(folder, execution)

    rows = [json.loads(line) for line in outcomes_path().read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["final_verdict"] == "fail"
    assert rows[0]["repair_attempts"] == 2


def test_record_execute_outcome_flag_gated(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_OUTCOME_LEDGER", raising=False)
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))

    folder = tmp_path / "sess-exec3"
    _write_run(folder)

    record_execute_outcome(folder, {"id": "exec-3", "oracle": {"verdict": "pass"}})
    assert not outcomes_path().exists()


def test_outcomes_root_env_isolates_turn_and_execute_ledgers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    isolated_root = tmp_path / "isolated-outcomes"
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(isolated_root))

    folder = tmp_path / "sess-isolated"
    _write_run(folder)

    record_turn_outcome(folder, 1)
    record_execute_outcome(folder, {"id": "exec-isolated", "oracle": {"verdict": "pass"}})

    ledger = isolated_root / ".agent-lab" / "outcomes.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert outcomes_path() == ledger
    assert [row["phase"] for row in rows] == ["turn", "execute"]
    assert not (tmp_path / ".agent-lab" / "outcomes.jsonl").exists()


def test_execute_after_turn_close_no_longer_loses_the_verdict(tmp_path, monkeypatch) -> None:
    """End-to-end shape of the real 2026-07 bug: a turn closes (no executions
    yet) *then* execute/verify resolves. Before this fix, the ledger's only
    row for this episode had final_verdict=null forever. Now the execute-phase
    row carries the real verdict, so feedback_report's clean-pass rate is no
    longer silently and permanently zero for this session.
    """
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))

    folder = tmp_path / "sess-e2e"
    _write_run(folder)  # executions=[] — mirrors turn-close-before-execute

    record_turn_outcome(folder, 1)  # Room turn closes first, no verdict yet

    execution = {"id": "exec-4", "oracle": {"verdict": "pass"}, "repair_history": []}
    record_execute_outcome(folder, execution)  # execute resolves afterward

    rows = [json.loads(line) for line in outcomes_path().read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 2
    assert rows[0]["phase"] == "turn"
    assert rows[0]["final_verdict"] is None  # the historically-broken row
    assert rows[1]["phase"] == "execute"
    assert rows[1]["final_verdict"] == "pass"  # the fix: verdict is now captured
