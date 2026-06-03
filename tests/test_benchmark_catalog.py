"""Offline room benchmark catalog checks (H-P2)."""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.plan_actions import parse_plan_action_sections
from agent_lab.session_score import score_session

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "sessions" / "_benchmark"


def _run(name: str) -> dict:
    return json.loads((BENCH / name / "run.json").read_text(encoding="utf-8"))


def _plan(name: str) -> str:
    return (BENCH / name / "plan.md").read_text(encoding="utf-8")


def test_benchmark_catalog_has_expected_scenarios():
    expected = {
        "analyze_1r_three_views",
        "plan_now_actions",
        "specialist_asymmetric_cwd",
        "delegate_codex",
        "ten_turn_kpi_stub",
    }
    actual = {p.name for p in BENCH.iterdir() if p.is_dir()}
    assert expected <= actual


def test_r1_analyze_three_views_score_under_duplicate_threshold():
    run = _run("analyze_1r_three_views")
    assert run["agent_parallel_rounds"] == 1
    report = score_session(BENCH / "analyze_1r_three_views")
    assert report["counts"]["duplicate_speech"]["agents"] == 3
    assert (report["scores"]["duplicate_speech_rate"] or 0.0) < 0.65


def test_r2_plan_now_actions_parser_shape():
    plan = _plan("plan_now_actions")
    sections = parse_plan_action_sections(plan)

    assert "## 지금 실행" in plan
    assert sections["recommended"]["action_key"] == "now:1"
    assert sections["recommended"]["expected_paths"] == [
        ".github/workflows/ci.yml",
        "./Makefile",
    ]
    assert sections["recommended"]["verification_paths"] == [
        "tests/test_session_score_ci.py"
    ]
    assert len(sections["all_executable"]) == 2


def test_r3_specialist_asymmetric_cwd_meta():
    run = _run("specialist_asymmetric_cwd")
    caps = run["agent_capabilities"]
    context_agents = run["last_turn"]["context"]["agents"]
    cwd_by_agent = {
        row["agent"]: row["capability_cwd"]
        for row in context_agents
    }
    round_by_agent = {
        row["agent"]: row["parallel_round"]
        for row in context_agents
    }

    assert run["turn_profile"] == "specialist"
    assert caps["cursor"]["cwd_role"] == "execute"
    assert caps["codex"]["cwd_role"] == "repo"
    assert caps["claude"]["cwd_role"] == "review"
    assert round_by_agent == {"codex": 1, "claude": 1, "cursor": 2}
    assert len(set(cwd_by_agent.values())) == 3
    assert cwd_by_agent["codex"].endswith("/repo")
    assert cwd_by_agent["claude"].endswith("/review")
    assert cwd_by_agent["cursor"].endswith("/execute")


def test_r4_delegate_codex_fixture_shape():
    run = _run("delegate_codex")
    delegate = run["last_delegate"]
    artifacts = run["artifacts"]

    assert delegate["agent"] == "codex"
    assert delegate["replaced_full_round"] is True
    assert delegate["artifact_id"] == "art-delegate-codex"
    assert any(a["kind"] == "delegate" and a["producer"] == "codex" for a in artifacts)


def test_r5_ten_turn_kpi_stub_score_shape():
    run = _run("ten_turn_kpi_stub")
    report = score_session(BENCH / "ten_turn_kpi_stub")

    assert len(run["turns"]) == 10
    for key in (
        "objection_resolution_rate",
        "execute_first_try_rate",
        "partial_turn_rate",
        "worktree_usage_rate",
        "merge_first_success_rate",
    ):
        assert key in report["scores"]
    assert report["scores"]["partial_turn_rate"] == 0.1
