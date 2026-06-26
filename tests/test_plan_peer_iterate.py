"""Plan peer ITERATE loop (P1-b)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_lab.plan_peer_iterate import parse_plan_peer_verdict
from agent_lab.plan_workflow import (
    effective_max_peer_review_rounds,
    get_plan_workflow,
    init_plan_workflow_on_plan_send,
    resolved_max_peer_review_rounds,
    set_plan_workflow_phase,
    tick_plan_workflow_after_turn,
)
from agent_lab.run_meta import patch_run_meta, read_run_meta


def test_resolved_max_peer_review_rounds_default() -> None:
    assert resolved_max_peer_review_rounds() == 2


def test_resolved_max_peer_review_rounds_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MAX_PEER_REVIEW_ROUNDS", "5")
    assert resolved_max_peer_review_rounds() == 5


def test_effective_max_peer_review_rounds_env_overrides_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MAX_PEER_REVIEW_ROUNDS", "1")
    pw = {"max_peer_review_rounds": 2}
    assert effective_max_peer_review_rounds(pw) == 1


def test_parse_plan_peer_verdict_iterate_and_accept() -> None:
    iterate_msg = {"role": "agent", "content": "act: CHALLENGE\nplan_action:1 scope too wide"}
    accept_msg = {"role": "agent", "content": "act: ENDORSE\nlooks good"}
    assert parse_plan_peer_verdict([iterate_msg]) == "iterate"
    assert parse_plan_peer_verdict([accept_msg]) == "accept"
    assert parse_plan_peer_verdict([iterate_msg, accept_msg]) == "iterate"


def test_tick_peer_iterate_verdict_moves_to_refine(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)

    def _peer_review(run: dict[str, Any]) -> dict[str, Any]:
        pw = get_plan_workflow(run)
        pw["phase"] = "PEER_REVIEW"
        pw["peer_review_round"] = 0
        pw["last_peer_verdict"] = "iterate"
        run["plan_workflow"] = pw
        return run

    patch_run_meta(folder, _peer_review)
    plan = "# plan\n"
    tick = tick_plan_workflow_after_turn(
        folder,
        synthesize=True,
        cancelled=False,
        plan_md=plan,
        plan_before=plan,
        has_pending_inbox_question=False,
    )
    assert tick.get("phase") == "REFINE"
    assert tick.get("peer_iterate") == "iterate"
