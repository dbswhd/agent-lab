"""Offline session KPI scoring (H4)."""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.session_score import score_session

ROOT = Path(__file__).resolve().parents[1]
REGRESSION = ROOT / "sessions" / "_regression"


def _write_session(
    folder: Path,
    *,
    run: dict,
    chat_lines: list[dict],
    plan_md: str,
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (folder / "chat.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in chat_lines) + "\n",
        encoding="utf-8",
    )
    (folder / "plan.md").write_text(plan_md, encoding="utf-8")


def test_mission_loop_kpis_when_enabled(tmp_path: Path) -> None:
    folder = tmp_path / "sess-mission"
    _write_session(
        folder,
        run={
            "mission_loop": {
                "enabled": True,
                "phase": "MISSION_PAUSED",
                "iteration": 2,
                "circuit_breaker": True,
                "action_repair_counts": {"1": 1},
            }
        },
        chat_lines=[{"role": "user", "content": "mission"}],
        plan_md="## 합의\n",
    )
    (folder / "learnings.md").write_text("x" * 250, encoding="utf-8")
    report = score_session(folder)
    assert report["counts"]["mission_loop"]["enabled"] == 1
    assert report["counts"]["mission_loop"]["repair_events"] == 1
    assert report["counts"]["mission_loop"]["notepad_chars"] == 250
    assert report["scores"]["mission_circuit_breaker"] == 1.0


def test_objection_resolution_rate(tmp_path: Path):
    folder = tmp_path / "sess-obj"
    _write_session(
        folder,
        run={
            "objections": [
                {"id": "o1", "status": "resolved_accepted", "act": "BLOCK"},
                {"id": "o2", "status": "open", "act": "CHALLENGE"},
            ]
        },
        chat_lines=[{"role": "user", "content": "hi"}],
        plan_md="## 합의\n",
    )
    report = score_session(folder)
    assert report["scores"]["objection_resolution_rate"] == 0.5
    assert report["counts"]["objections"]["total"] == 2


def test_execute_first_try_rate(tmp_path: Path):
    folder = tmp_path / "sess-exec"
    _write_session(
        folder,
        run={
            "executions": [
                {
                    "id": "e1",
                    "action_index": 1,
                    "status": "rejected",
                },
                {
                    "id": "e2",
                    "action_index": 1,
                    "status": "completed",
                },
                {
                    "id": "e3",
                    "action_index": 2,
                    "status": "completed",
                },
            ]
        },
        chat_lines=[{"role": "user", "content": "go"}],
        plan_md="## 합의\n",
    )
    report = score_session(folder)
    assert abs(report["scores"]["execute_first_try_rate"] - 2 / 3) < 1e-6
    assert report["counts"]["executions"]["first_try"] == 2
    assert report["counts"]["executions"]["retried"] == 1


def test_execute_merge_kpis(tmp_path: Path):
    folder = tmp_path / "sess-merge"
    _write_session(
        folder,
        run={
            "executions": [
                {
                    "id": "e1",
                    "action_index": 1,
                    "status": "merged",
                    "isolation_effective": "worktree",
                    "git_root": "/repo",
                    "merge": {"status": "merged", "commit_sha": "abc"},
                },
                {
                    "id": "e2",
                    "action_index": 2,
                    "status": "merge_conflict",
                    "isolation_effective": "worktree",
                    "git_root": "/repo",
                    "merge": {"status": "conflict", "conflict_files": ["x.py"]},
                },
                {
                    "id": "e3",
                    "action_index": 3,
                    "status": "pending_approval",
                    "isolation_effective": "snapshot_override",
                    "git_root": "/repo",
                },
                {
                    "id": "e4",
                    "action_index": 4,
                    "status": "completed",
                    "isolation_effective": "apply",
                },
            ]
        },
        chat_lines=[{"role": "user", "content": "go"}],
        plan_md="## 합의\n",
    )
    report = score_session(folder)

    assert report["scores"]["worktree_usage_rate"] == 2 / 3
    assert report["scores"]["snapshot_override_rate"] == 1 / 4
    assert report["scores"]["merge_first_success_rate"] == 1 / 2
    assert report["scores"]["merge_conflict_rate"] == 1 / 2
    assert report["counts"]["execute_merge"]["worktree"] == 2
    assert any("merge first-success" in line for line in report["summary_lines"])


def test_partial_turn_rate(tmp_path: Path):
    folder = tmp_path / "sess-partial"
    _write_session(
        folder,
        run={
            "turns": [
                {"mode": "discuss", "status": "completed"},
                {
                    "mode": "discuss",
                    "status": "partial",
                    "failed_agents": ["claude"],
                    "succeeded_agents": ["cursor"],
                },
            ]
        },
        chat_lines=[{"role": "user", "content": "go"}],
        plan_md="## 합의\n",
    )
    report = score_session(folder)

    assert report["scores"]["partial_turn_rate"] == 0.5
    assert report["counts"]["turns"]["partial"] == 1
    assert any("partial turns" in line for line in report["summary_lines"])


def test_specialist_capability_cwd_kpis_from_fixture():
    report = score_session(REGRESSION / "specialist_asymmetric_cwd")

    assert report["scores"]["specialist_context_recorded"] == 1.0
    assert report["scores"]["asymmetric_capability_cwd"] == 1.0
    assert report["scores"]["capability_cwd_agent_count"] == 3.0
    assert report["counts"]["capability_cwd"]["agent_count"] == 3
    assert report["counts"]["capability_cwd"]["distinct_cwd"] == 3
    assert any("specialist context cwd" in line for line in report["summary_lines"])


def test_specialist_capability_cwd_missing_is_recorded_false(tmp_path: Path):
    folder = tmp_path / "sess-specialist-missing-cwd"
    _write_session(
        folder,
        run={
            "turn_profile": "specialist",
            "last_turn": {
                "turn_profile": "specialist",
                "context": {"agents": [{"agent": "codex", "parallel_round": 1}]},
            },
        },
        chat_lines=[{"role": "user", "content": "go"}],
        plan_md="## 합의\n",
    )

    report = score_session(folder)

    assert report["scores"]["specialist_context_recorded"] == 0.0
    assert report["scores"]["asymmetric_capability_cwd"] == 0.0
    assert report["scores"]["capability_cwd_agent_count"] == 0.0
    assert report["counts"]["capability_cwd"]["specialist_contexts"] == 1


def test_ref_validity_and_duplicate_speech(tmp_path: Path):
    folder = tmp_path / "sess-mix"
    _write_session(
        folder,
        run={},
        chat_lines=[
            {"role": "user", "content": "q"},
            {
                "role": "agent",
                "agent": "codex",
                "content": "동일한 첫 문장으로 시작하는 긴 의견입니다 alpha beta",
            },
            {
                "role": "agent",
                "agent": "claude",
                "content": "동일한 첫 문장으로 시작하는 긴 의견입니다 gamma delta",
            },
        ],
        plan_md="## 합의\n- item (ref: chat.jsonl#L1)\n",
    )
    report = score_session(folder)
    assert report["scores"]["ref_validity_rate"] == 1.0
    assert report["scores"]["duplicate_speech_rate"] is not None
    assert report["counts"]["duplicate_speech"]["pairs"] >= 1
