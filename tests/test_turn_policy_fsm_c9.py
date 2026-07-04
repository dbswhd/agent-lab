"""C9 — TurnPolicy FSM advance bypasses legacy synthesize gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.plan.workflow import (
    init_plan_workflow_on_plan_send,
    plan_workflow_phase,
    tick_plan_workflow_after_turn,
)
from agent_lab.room.turn_policy import TurnPolicyEngine, TurnSignals, _run_fsm_tick, turn_policy_enabled
from agent_lab.run.meta import patch_run_meta, read_run_meta


def _seed_clarity_gate_goal(folder: Path) -> None:
    patch_run_meta(
        folder,
        lambda r: {
            **r,
            "verified_loop": {
                **(r.get("verified_loop") or {}),
                "loop_goal": {"text": "fix src/agent_lab/run_meta.py null check"},
            },
        },
    )


def test_tick_plan_workflow_turn_policy_bypasses_discuss_only_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "0")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    _seed_clarity_gate_goal(folder)

    legacy = tick_plan_workflow_after_turn(
        folder,
        synthesize=False,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
    )
    assert legacy.get("discuss_only") is True
    assert legacy.get("advance") is None

    bypass = tick_plan_workflow_after_turn(
        folder,
        synthesize=False,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
        turn_policy_advance=True,
    )
    assert bypass.get("discuss_only") is not True
    assert bypass.get("advance") == "DRAFT"
    assert plan_workflow_phase(read_run_meta(folder)) == "DRAFT"


def test_run_fsm_tick_advances_clarify_on_discuss_when_turn_policy_on(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "0")
    assert turn_policy_enabled()
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    _seed_clarity_gate_goal(folder)
    run_meta = read_run_meta(folder)
    run_meta["room_preset"] = "supervisor"

    plan_md, run_meta, pw_force_scribe = _run_fsm_tick(
        folder,
        run_meta=run_meta,
        plan_md="",
        plan_before="",
        synthesize=False,
        cancelled=False,
        on_event=None,
    )
    assert plan_workflow_phase(run_meta) == "DRAFT"
    assert pw_force_scribe is True


def test_apply_turn_effects_fsm_tick_on_supervisor_discuss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.room.turn_policy import apply_turn_effects

    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "0")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    _seed_clarity_gate_goal(folder)
    run_meta = read_run_meta(folder)
    run_meta["room_preset"] = "supervisor"

    signals = TurnSignals.from_run_meta(
        run_meta,
        supervisor_first_turn=False,
    )
    effects = TurnPolicyEngine.resolve(signals)
    assert effects.advance_plan_workflow is True

    result = apply_turn_effects(
        signals=signals,
        folder=folder,
        topic="continue clarify",
        messages=[],
        run_meta=run_meta,
        plan_before="",
        mode="discuss",
        cancelled=False,
        human_turn=2,
    )
    assert result.applied is True
    assert plan_workflow_phase(read_run_meta(folder)) == "DRAFT"
