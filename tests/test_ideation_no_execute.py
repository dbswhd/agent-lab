"""RI-04 — no path on the idea lane activates execution.

Covers the three entry points named in the plan (§4.2): legacy `plan/approve`,
the template fast-path that skips HUMAN_PENDING, and a direct execute API call.
Existing sessions must keep approving and executing exactly as before.
"""

from __future__ import annotations

import subprocess

import pytest

from agent_lab import ideation
from agent_lab.plan.workflow import PlanWorkflowNotApproved, ensure_plan_workflow_approved
from agent_lab.plan.workflow_approval import (
    IDEATION_NO_EXECUTE_REASON,
    approve_plan,
    approve_plan_bypass,
)
from agent_lab.run.meta import read_run_meta, write_run_meta
from agent_lab.run.state import RunState
from agent_lab.turn_modes import approval_starts_execute_loop

PLAN_MD = """# Plan

## Goal
첫 작업을 시작한다

## Actions
- [ ] 무언가 한다
  - 검증: pytest
"""


@pytest.fixture()
def no_subprocess(monkeypatch):
    """Spy: nothing in this module may shell out (no worktree, no executor)."""
    calls: list[object] = []

    def _boom(*args, **kwargs):
        calls.append(args)
        raise AssertionError(f"unexpected subprocess call: {args!r}")

    for name in ("run", "check_output", "check_call", "Popen", "call"):
        monkeypatch.setattr(subprocess, name, _boom)
    return calls


def _session(tmp_path, *, ideation_stage: str | None, plan_phase: str | None = "APPROVED"):
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text(PLAN_MD, encoding="utf-8")
    from agent_lab.plan.pending import plan_content_hash

    run: dict = {"topic": "개념"}
    if plan_phase is not None:
        run["plan_workflow"] = {
            "enabled": True,
            "phase": plan_phase,
            "plan_hash_at_approval": plan_content_hash(PLAN_MD),
        }
    state = RunState.from_memory(run)
    if ideation_stage is not None:
        payload = ideation.new_ideation(original_concept="개념")
        payload["stage"] = ideation_stage
        ideation.start_ideation(state, payload)
    write_run_meta(folder, dict(state))
    return folder


ALL_STAGES = [ideation.STAGE_EXPLORE, ideation.STAGE_SHAPE, ideation.STAGE_PLAN]


# --- the shared execute gate --------------------------------------------


@pytest.mark.parametrize("stage", ALL_STAGES)
def test_execute_gate_refuses_every_ideation_stage(tmp_path, no_subprocess, stage):
    """Reaching `plan` stage means "write me a plan", never "run it" (§4.2)."""
    folder = _session(tmp_path, ideation_stage=stage)
    with pytest.raises(PlanWorkflowNotApproved) as excinfo:
        ensure_plan_workflow_approved(folder)
    assert str(excinfo.value) == IDEATION_NO_EXECUTE_REASON


def test_execute_gate_refuses_ideation_without_a_plan_workflow(tmp_path, no_subprocess):
    """The hole this closes: no plan_workflow used to mean "gate not applicable"."""
    folder = _session(tmp_path, ideation_stage=ideation.STAGE_PLAN, plan_phase=None)
    with pytest.raises(PlanWorkflowNotApproved):
        ensure_plan_workflow_approved(folder)


def test_direct_dry_run_call_does_not_reach_a_worktree(tmp_path, no_subprocess, monkeypatch):
    """An execute API call that skips the UI still stops at the shared gate."""
    from agent_lab.plan import execute as plan_execute

    monkeypatch.setattr(plan_execute, "_execute_agent_available", lambda executor: True)
    folder = _session(tmp_path, ideation_stage=ideation.STAGE_PLAN)

    with pytest.raises(RuntimeError, match="plan workflow approval required"):
        plan_execute.run_dry_run(folder, action_index=0, executor="cursor")
    assert no_subprocess == []


# --- approval entry points ----------------------------------------------


@pytest.mark.parametrize("stage", ALL_STAGES)
def test_legacy_plan_approve_is_refused(tmp_path, no_subprocess, stage):
    folder = _session(tmp_path, ideation_stage=stage, plan_phase="HUMAN_PENDING")
    with pytest.raises(PlanWorkflowNotApproved) as excinfo:
        approve_plan(folder)
    assert str(excinfo.value) == IDEATION_NO_EXECUTE_REASON


@pytest.mark.parametrize("stage", ALL_STAGES)
def test_template_fast_path_is_refused(tmp_path, no_subprocess, stage):
    """`approve_plan_bypass` skips HUMAN_PENDING — it must not become a side door."""
    folder = _session(tmp_path, ideation_stage=stage, plan_phase=None)
    with pytest.raises(PlanWorkflowNotApproved) as excinfo:
        approve_plan_bypass(folder, goal="목표")
    assert str(excinfo.value) == IDEATION_NO_EXECUTE_REASON


@pytest.mark.parametrize("stage", ALL_STAGES)
def test_a_refused_approval_leaves_no_trace(tmp_path, no_subprocess, stage):
    folder = _session(tmp_path, ideation_stage=stage, plan_phase="HUMAN_PENDING")
    before = read_run_meta(folder)
    with pytest.raises(PlanWorkflowNotApproved):
        approve_plan(folder)
    after = read_run_meta(folder)

    assert after == before
    assert "mission_loop" not in after
    assert "goal_loop" not in after
    assert "verified_loop" not in after
    assert not after.get("executions")


def test_approval_never_starts_a_loop_on_the_idea_lane():
    run = RunState.from_memory({"topic": "개념", "plan_intent": "loop"})
    ideation.start_ideation(run, ideation.new_ideation())
    assert approval_starts_execute_loop(dict(run)) is False


# --- copy / select still work -------------------------------------------


def test_selecting_an_option_is_not_an_approval(tmp_path, no_subprocess):
    run = RunState.from_memory({"topic": "개념"})
    ideation.start_ideation(run, ideation.new_ideation())
    ideation.mutate_ideation(run, ideation.set_options([{"id": "opt-a", "title": "A"}]))
    state = ideation.mutate_ideation(run, ideation.select_option("opt-a", reason="이유"))

    assert state["selection"]["option_id"] == "opt-a"
    assert "plan_workflow" not in run
    assert approval_starts_execute_loop(dict(run)) is False
    assert no_subprocess == []


def test_reading_state_for_export_starts_nothing(tmp_path, no_subprocess):
    folder = _session(tmp_path, ideation_stage=ideation.STAGE_PLAN)
    run = read_run_meta(folder)
    assert ideation.read_ideation(run) is not None
    assert (folder / "plan.md").read_text(encoding="utf-8") == PLAN_MD
    assert no_subprocess == []


# --- existing sessions ---------------------------------------------------


def test_existing_session_still_passes_the_gate(tmp_path):
    folder = _session(tmp_path, ideation_stage=None)
    ensure_plan_workflow_approved(folder)  # does not raise


def test_existing_session_still_approves(tmp_path):
    folder = _session(tmp_path, ideation_stage=None, plan_phase="HUMAN_PENDING")
    result = approve_plan(folder, goal="목표")
    assert result
    assert read_run_meta(folder)["plan_workflow"]["phase"] == "APPROVED"


def test_existing_session_still_uses_the_template_fast_path(tmp_path):
    folder = _session(tmp_path, ideation_stage=None, plan_phase=None)
    result = approve_plan_bypass(folder, goal="목표")
    assert result
    assert read_run_meta(folder)["plan_workflow"]["phase"] == "APPROVED"


def test_existing_session_approval_still_starts_a_loop():
    assert approval_starts_execute_loop({"topic": "t", "plan_intent": "loop"}) is True
    assert approval_starts_execute_loop(None) is True
