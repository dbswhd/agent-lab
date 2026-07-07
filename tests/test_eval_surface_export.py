"""Eval Surface v1 — trace_export unit tests (synthetic session dirs, no I/O beyond tmp_path)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evals.trace_export import FIXED_SPAN_NAMES, export_session_trace


def _write_run_json(session_dir: Path, run: dict[str, Any]) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_missing_run_json_is_fail_open(tmp_path: Path) -> None:
    session_dir = tmp_path / "empty_session"
    session_dir.mkdir()
    trace = export_session_trace(session_dir, case_id="X")
    assert trace["session_id"] == "empty_session"
    assert trace["spans"] == []
    assert trace["artifacts"]["executions"] == []
    assert trace["artifacts"]["message_count"] == 0
    assert trace["artifacts"]["session_status"] == ""
    assert trace["outcome"]["final_oracle_verdict"] is None


def test_minimal_run_json_only_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "minimal"
    _write_run_json(session_dir, {"topic": "t", "turns": [{"mode": "plan"}]})
    trace = export_session_trace(session_dir)
    present = {s["name"] for s in trace["spans"]}
    assert present == {"route", "room_round"}  # turn presence implies a minimal route + round signal


def test_full_session_synthesizes_expected_spans(tmp_path: Path) -> None:
    session_dir = tmp_path / "full"
    _write_run_json(
        session_dir,
        {
            "topic": "full session",
            "workflow_id": "room.parallel",
            "agents": ["cursor", "codex"],
            "message_count": 3,
            "agent_parallel_rounds": 1,
            "status": "completed",
            "synthesize": True,
            "turns": [
                {
                    "mode": "discuss",
                    "succeeded_agents": ["cursor", "codex"],
                    "category": {"value": "deep", "source": "heuristic"},
                    "communicate_meta": {
                        "act_counts": {"PROPOSE": 1, "CHALLENGE": 1},
                        "agent_reply_count": 2,
                        "envelope_parse_error_count": 0,
                    },
                }
            ],
            "objections": [{"act": "BLOCK", "status": "open"}],
            "actions": [{"action_id": "a1", "what": "x", "where": "y", "verify": "z"}],
            "approvals": [{"id": "appr-1"}],
            "executions": [{"id": "e1", "oracle": {"verdict": "pass"}}],
        },
    )
    trace = export_session_trace(session_dir, case_id="FULL")
    present = {s["name"] for s in trace["spans"]}
    assert present == {
        "route",
        "role_plan",
        "room_round",
        "objection",
        "plan_update",
        "human_gate",
        "execute",
        "oracle_verify",
    }
    assert trace["outcome"]["final_oracle_verdict"] == "pass"
    assert trace["case_id"] == "FULL"
    assert trace["artifacts"]["agents"] == ["cursor", "codex"]
    assert trace["artifacts"]["succeeded_agents"] == ["cursor", "codex"]
    assert trace["artifacts"]["message_count"] == 3
    assert trace["artifacts"]["agent_reply_count"] == 2
    assert trace["artifacts"]["session_status"] == "completed"


def test_plan_and_human_gate_signals_can_be_reconstructed_without_actions_or_approvals(tmp_path: Path) -> None:
    session_dir = tmp_path / "plan_approved"
    _write_run_json(
        session_dir,
        {
            "topic": "approved workflow",
            "workflow_id": "room.parallel",
            "turns": [{"mode": "plan", "status": "completed"}],
            "plan_workflow": {
                "enabled": True,
                "phase": "APPROVED",
                "approved_at": "2026-06-14T00:00:02+00:00",
                "approved_by": "human",
            },
            "verified_loop": {
                "loop_goal": {
                    "text": "Demo feature",
                    "approved_at": "2026-06-14T00:00:02+00:00",
                    "approved_by": "human",
                }
            },
        },
    )
    trace = export_session_trace(session_dir)
    present = {s["name"] for s in trace["spans"]}
    assert "plan_update" in present
    assert "human_gate" in present


def test_oracle_and_feedback_spans_use_execution_and_reply_policy_fallbacks(tmp_path: Path) -> None:
    session_dir = tmp_path / "oracle_fallbacks"
    _write_run_json(
        session_dir,
        {
            "topic": "oracle fallback",
            "workflow_id": "room.parallel",
            "turns": [
                {
                    "mode": "discuss",
                    "communicate_meta": {
                        "reply_policy": {"mode": "history", "rationale": "evidence=execute"},
                    },
                }
            ],
            "executions": [
                {
                    "id": "e1",
                    "status": "merged",
                    "oracle_verdict": "pass",
                    "verify_after_merge": {"status": "passed"},
                }
            ],
            "mission_loop": {"phase": "VERIFY", "last_verify": {"status": "pass"}},
        },
    )
    trace = export_session_trace(session_dir)
    present = {s["name"] for s in trace["spans"]}
    assert "oracle_verify" in present
    assert "feedback_advisor" in present
    assert trace["outcome"]["final_oracle_verdict"] == "pass"


def test_evidence_ledger_rows_can_reconstruct_execute_and_human_gate(tmp_path: Path) -> None:
    session_dir = tmp_path / "evidence"
    _write_run_json(
        session_dir,
        {
            "topic": "evidence ledger",
            "workflow_id": "room.parallel",
            "turns": [{"mode": "discuss", "status": "completed"}],
            "mission_loop": {"phase": "MERGE_REVIEW", "plan_gate": {"status": "ok"}},
            "evidence_ledger": {"path_suffix": "evidence.jsonl", "entry_count": 2},
        },
    )
    _write_jsonl(
        session_dir / "evidence.jsonl",
        [
            {"phase": "DRY_RUN", "kind": "dry_run", "detail": "mock dry-run complete"},
            {"phase": "MERGE", "kind": "merge_approve", "detail": "human approved merge"},
        ],
    )
    trace = export_session_trace(session_dir)
    present = {s["name"] for s in trace["spans"]}
    assert "execute" in present
    assert "human_gate" in present


def test_block_target_ref_can_imply_plan_update_and_role_participants(tmp_path: Path) -> None:
    session_dir = tmp_path / "block_target"
    _write_run_json(
        session_dir,
        {
            "topic": "block target ref",
            "workflow_id": "room",
            "objections": [
                {
                    "from": "claude",
                    "act": "BLOCK",
                    "status": "open",
                    "target_ref": "plan_action:1",
                    "plan_action_index": 1,
                }
            ],
            "turns": [{"mode": "plan", "status": "completed"}],
        },
    )
    trace = export_session_trace(session_dir)
    present = {s["name"] for s in trace["spans"]}
    assert "plan_update" in present
    assert "role_plan" in present


def test_malformed_run_json_is_fail_open(tmp_path: Path) -> None:
    session_dir = tmp_path / "malformed"
    session_dir.mkdir()
    (session_dir / "run.json").write_text("{not valid json", encoding="utf-8")
    trace = export_session_trace(session_dir)
    assert trace["spans"] == []
    assert trace["topic"] == ""


def test_fixed_span_names_are_stable() -> None:
    # v1 span-name contract (EVAL-SURFACE-V1-PLAN.md) — changing this list is a breaking change.
    assert FIXED_SPAN_NAMES == (
        "route",
        "role_plan",
        "room_round",
        "objection",
        "plan_update",
        "human_gate",
        "execute",
        "oracle_verify",
        "feedback_advisor",
    )
