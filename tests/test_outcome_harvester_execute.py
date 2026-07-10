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


def test_record_execute_outcome_persists_contract_and_regret(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))

    folder = tmp_path / "sess-contract"
    _write_run(folder)
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    run["turn_contract"] = {
        "contract_id": "quick_read",
        "source": "shadow",
        "safety_floor": "quick_read",
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")

    record_execute_outcome(
        folder,
        {
            "id": "exec-contract",
            "oracle": {"verdict": "fail"},
            "repair_history": [{"attempt": 1}],
        },
    )

    row = json.loads(outcomes_path().read_text(encoding="utf-8").splitlines()[0])
    assert row["contract_id"] == "quick_read"
    assert row["contract_source"] == "shadow"
    assert row["route_regret_signals"] == ["under_routed"]


def test_record_execute_outcome_tags_harness_infra_on_skipped_verdict(tmp_path, monkeypatch) -> None:
    """HS1-1: execute rows independently derive harness_infra from Oracle "skipped"
    (missing 검증: criterion) — same signal eval_harness.score_outcome_verdict uses."""
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))

    folder = tmp_path / "sess-skip"
    _write_run(folder)

    execution = {"id": "exec-1", "oracle": {"verdict": "skipped"}, "repair_history": []}
    record_execute_outcome(folder, execution)

    row = json.loads(outcomes_path().read_text(encoding="utf-8").splitlines()[0])
    assert row["failure_tags"] == ["harness_infra"]
    assert row["primary_tag"] == "harness_infra"


def test_record_execute_outcome_no_failure_tags_on_evidenced_pass(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))

    folder = tmp_path / "sess-pass"
    _write_run(folder)

    execution = {
        "id": "exec-1",
        "oracle": {"verdict": "pass", "evidence": ["found literal(s): retry_strategy"]},
        "repair_history": [],
    }
    record_execute_outcome(folder, execution)

    row = json.loads(outcomes_path().read_text(encoding="utf-8").splitlines()[0])
    assert row["failure_tags"] == []
    assert row["primary_tag"] is None


def test_record_execute_outcome_tags_false_success_on_pass_without_evidence(tmp_path, monkeypatch) -> None:
    """HS1-1: the execute row is where Oracle verdicts actually live (turn rows
    close before verify runs), so pass-with-no-cited-evidence must be tagged
    here — before this, false_success was structurally dead (2026-07-09 audit:
    195/197 turn rows had final_verdict null, execute rows never derived it)."""
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))

    folder = tmp_path / "sess-bare-pass"
    _write_run(folder)

    execution = {"id": "exec-1", "oracle": {"verdict": "pass", "evidence": []}, "repair_history": []}
    record_execute_outcome(folder, execution)

    row = json.loads(outcomes_path().read_text(encoding="utf-8").splitlines()[0])
    assert row["failure_tags"] == ["false_success"]
    assert row["primary_tag"] == "false_success"


def test_record_execute_outcome_tags_self_patch_eligible(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))

    folder = tmp_path / "sess-exec"
    _write_run(folder)

    execution = {
        "id": "exec-2",
        "oracle": {"verdict": "pass"},
        "repair_history": [],
        "source_touched_paths": [".claude/skills/foo/SKILL.md"],
    }
    record_execute_outcome(folder, execution)

    rows = [json.loads(line) for line in outcomes_path().read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["self_patch"]["eligible"] is True
    assert rows[0]["self_patch"]["core_paths"] == []


def test_record_execute_outcome_tags_self_patch_ineligible_on_core_touch(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))

    folder = tmp_path / "sess-exec"
    _write_run(folder)

    execution = {
        "id": "exec-3",
        "oracle": {"verdict": "pass"},
        "repair_history": [],
        "source_touched_paths": [".claude/skills/foo/SKILL.md", "src/agent_lab/room/turn_flow_run.py"],
    }
    record_execute_outcome(folder, execution)

    rows = [json.loads(line) for line in outcomes_path().read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["self_patch"]["eligible"] is False
    assert rows[0]["self_patch"]["core_paths"] == ["src/agent_lab/room/turn_flow_run.py"]


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


def test_record_execute_outcome_reads_advisor_from_turn_metrics(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))

    folder = tmp_path / "sess-metrics"
    folder.mkdir()
    run = {
        "topic": "JWT path in src/auth.py — pick retry strategy.",
        "turns": [
            {
                **_TURN,
                "category": {"value": "standard", "source": "heuristic"},
                "turn_metrics": {
                    "advisor_source": "history",
                    "advisor_combo_id": "combo-1",
                },
            },
        ],
        "objections": [],
        "executions": [],
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")

    record_execute_outcome(folder, {"id": "exec-metrics", "oracle": {"verdict": "pass"}})

    rows = [json.loads(line) for line in outcomes_path().read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["phase"] == "execute"
    assert rows[0]["advisor_source"] == "history"
    assert rows[0]["combo_id"] == "combo-1"


def test_record_mock_execute_outcome_emits_structural_lift_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_OUTCOME_LEDGER", "1")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("AGENT_LAB_DOGFOOD_EXECUTE_OUTCOMES", "1")

    folder = tmp_path / "sess-mock-lift"
    _write_run(
        folder,
        executions=[],
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    run["turns"] = [
        {
            **_TURN,
            "category": {
                "value": "standard",
                "source": "heuristic",
                "advisor_source": "history",
            },
        },
    ]
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")

    from agent_lab.outcome_harvester import record_mock_execute_outcome

    record_mock_execute_outcome(folder)

    rows = [json.loads(line) for line in outcomes_path().read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["phase"] == "execute"
    assert rows[0]["advisor_source"] == "history"
    assert rows[0]["final_verdict"] == "pass"
