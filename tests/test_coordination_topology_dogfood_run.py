"""Coordination-topology shadow dogfood run — real room.run_room() + mock agents."""

from __future__ import annotations

from pathlib import Path

from scripts.coordination_topology_dogfood_run import run_dogfood


def test_run_dogfood_produces_a_shadow_decision_per_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")

    results = run_dogfood(tmp_path, topics=("오타 수정", "이 PR 코드 리뷰해줘 — 피드백 부탁드립니다."))
    assert len(results) == 2
    assert all("error" not in r for r in results)
    assert all(r["coordination_topology"] for r in results)
    assert (tmp_path / results[0]["session_id"] / "run.json").is_file()
