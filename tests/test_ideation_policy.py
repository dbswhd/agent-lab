"""RI-03 — no plan/execute side effects on the idea lane's exploration path."""

from __future__ import annotations

import pytest

from agent_lab import ideation
from agent_lab.room.plan_scribe import _should_scribe_plan_after_turn
from agent_lab.room.turn_policy_models import TurnPolicyEngine, TurnSignals
from agent_lab.run.state import RunState


def _ideation_run(stage: str = ideation.STAGE_EXPLORE, **extra) -> RunState:
    run = RunState.from_memory({"topic": "막연한 개념", **extra})
    state = ideation.new_ideation(original_concept="막연한 개념")
    state["stage"] = stage
    ideation.start_ideation(run, state)
    return run


def _legacy_run(**extra) -> RunState:
    return RunState.from_memory({"topic": "실행할 작업", **extra})


# --- TurnEffects ---------------------------------------------------------


@pytest.mark.parametrize("stage", [ideation.STAGE_EXPLORE, ideation.STAGE_SHAPE])
def test_exploration_turn_runs_agents_and_nothing_else(stage):
    effects = TurnPolicyEngine.resolve(TurnSignals(ideation_stage=stage, supervisor_first_turn=True))

    assert effects.run_agent_round is True
    assert effects.run_scribe is False
    assert effects.scribe_trigger == "none"
    assert effects.init_plan_workflow is False
    assert effects.advance_plan_workflow is False
    assert effects.assign_task_owners is False
    assert effects.turn_kind == "agent_turn"


@pytest.mark.parametrize("stage", [ideation.STAGE_EXPLORE, ideation.STAGE_SHAPE])
def test_consensus_does_not_open_the_scribe_while_exploring(stage):
    """Agreement between agents is not the user's decision (§1)."""
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            ideation_stage=stage,
            consensus_mode=True,
            consensus_status="reached",
            pending_agreement_count=3,
        )
    )
    assert effects.run_scribe is False
    assert effects.assign_task_owners is False


@pytest.mark.parametrize("stage", [ideation.STAGE_EXPLORE, ideation.STAGE_SHAPE])
def test_skill_intent_does_not_open_the_scribe_while_exploring(stage):
    effects = TurnPolicyEngine.resolve(TurnSignals(ideation_stage=stage, skill_intent="plan", proposed_tags_count=9))
    assert effects.run_scribe is False


def test_synthesize_only_does_not_write_a_plan_while_exploring():
    """A refresh/synthesize is not an explicit "make a plan" request."""
    effects = TurnPolicyEngine.resolve(TurnSignals(ideation_stage=ideation.STAGE_EXPLORE, synthesize_only=True))
    assert effects.run_agent_round is False
    assert effects.run_scribe is False
    assert effects.scribe_trigger == "none"


def test_plan_stage_restores_the_normal_scribe_path():
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            ideation_stage=ideation.STAGE_PLAN,
            plan_workflow_active=True,
            plan_workflow_phase="DRAFT",
            roster_size=3,
        )
    )
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "plan_workflow_draft"


def test_synthesize_only_still_scribes_at_plan_stage():
    effects = TurnPolicyEngine.resolve(TurnSignals(ideation_stage=ideation.STAGE_PLAN, synthesize_only=True))
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "synthesize_only"


def test_cancelled_turn_is_unchanged_on_the_idea_lane():
    effects = TurnPolicyEngine.resolve(TurnSignals(ideation_stage=ideation.STAGE_EXPLORE, cancelled=True))
    assert effects.run_scribe is False
    assert effects.turn_kind == "agent_turn"


# --- existing sessions ---------------------------------------------------


def test_legacy_supervisor_turn_still_bootstraps_the_plan_fsm():
    effects = TurnPolicyEngine.resolve(TurnSignals(supervisor_first_turn=True, roster_size=3))
    assert effects.init_plan_workflow is True
    assert effects.advance_plan_workflow is True


def test_legacy_consensus_still_opens_the_scribe():
    effects = TurnPolicyEngine.resolve(
        TurnSignals(consensus_status="reached", pending_agreement_count=2, roster_size=3)
    )
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "consensus_reached"
    assert effects.assign_task_owners is True


def test_signals_from_run_meta_carry_the_stage():
    assert TurnSignals.from_run_meta(_ideation_run()).ideation_stage == ideation.STAGE_EXPLORE
    assert TurnSignals.from_run_meta(_ideation_run(ideation.STAGE_PLAN)).ideation_stage == ideation.STAGE_PLAN
    assert TurnSignals.from_run_meta(_legacy_run()).ideation_stage is None


def test_routing_snapshot_records_the_stage():
    snapshot = TurnSignals.from_run_meta(_ideation_run()).routing_contract_snapshot()
    assert snapshot["ideation_stage"] == ideation.STAGE_EXPLORE
    assert TurnSignals.from_run_meta(_legacy_run()).routing_contract_snapshot()["ideation_stage"] is None


# --- auto scribe ---------------------------------------------------------


@pytest.mark.parametrize("stage", [ideation.STAGE_EXPLORE, ideation.STAGE_SHAPE])
def test_auto_scribe_stays_closed_while_exploring(stage):
    run = _ideation_run(stage)
    assert _should_scribe_plan_after_turn(synthesize=False, cancelled=False, run_meta=run) is False
    assert _should_scribe_plan_after_turn(synthesize=True, cancelled=False, run_meta=run) is False
    assert _should_scribe_plan_after_turn(synthesize=False, cancelled=False, run_meta=run, user_plan_send=True) is False


def test_auto_scribe_reopens_at_plan_stage():
    run = _ideation_run(ideation.STAGE_PLAN)
    assert _should_scribe_plan_after_turn(synthesize=True, cancelled=False, run_meta=run) is True


def test_auto_scribe_unchanged_for_existing_sessions():
    assert _should_scribe_plan_after_turn(synthesize=True, cancelled=False, run_meta=_legacy_run()) is True
    assert _should_scribe_plan_after_turn(synthesize=True, cancelled=True, run_meta=_legacy_run()) is False


# --- routing inputs ------------------------------------------------------


def test_execute_history_is_not_an_idea_quality_signal():
    assert ideation.uses_execute_history_routing(_ideation_run()) is False
    assert ideation.uses_execute_history_routing(_ideation_run(ideation.STAGE_PLAN)) is False
    assert ideation.uses_execute_history_routing(_legacy_run()) is True


def test_predicates_are_inert_without_ideation_state():
    legacy = _legacy_run()
    assert ideation.ideation_stage(legacy) is None
    assert ideation.suppresses_plan_side_effects(legacy) is False
    assert ideation.allows_scribe(legacy) is True
    assert ideation.suppresses_plan_side_effects(None) is False
    assert ideation.allows_scribe(None) is True


# --- session GET auto-sync ----------------------------------------------


def _write(folder, run):
    from agent_lab.run.meta import write_run_meta

    write_run_meta(folder, dict(run))


@pytest.mark.parametrize("stage", [ideation.STAGE_EXPLORE, ideation.STAGE_SHAPE])
def test_session_get_autosync_writes_no_plan_while_exploring(tmp_path, monkeypatch, stage):
    """Reading or refreshing a session must not synthesize a plan (§4.2)."""
    from agent_lab.room import turn_meta

    calls: list[str] = []
    monkeypatch.setattr(turn_meta, "ensure_consensus_plan_sync", lambda folder: calls.append("consensus"))
    monkeypatch.setattr(turn_meta, "ensure_verified_plan_sync", lambda folder: calls.append("verified"))

    _write(tmp_path, _ideation_run(stage))
    assert turn_meta.ensure_session_plan_pipeline(tmp_path) is False
    assert calls == []


def test_session_get_autosync_runs_at_plan_stage(tmp_path, monkeypatch):
    from agent_lab.room import turn_meta

    calls: list[str] = []
    monkeypatch.setattr(turn_meta, "ensure_consensus_plan_sync", lambda folder: (calls.append("consensus"), False)[1])
    monkeypatch.setattr(turn_meta, "ensure_verified_plan_sync", lambda folder: (calls.append("verified"), False)[1])

    _write(tmp_path, _ideation_run(ideation.STAGE_PLAN))
    turn_meta.ensure_session_plan_pipeline(tmp_path)
    assert calls == ["consensus", "verified"]


def test_session_get_autosync_unchanged_for_existing_sessions(tmp_path, monkeypatch):
    from agent_lab.room import turn_meta

    calls: list[str] = []
    monkeypatch.setattr(turn_meta, "ensure_consensus_plan_sync", lambda folder: (calls.append("consensus"), False)[1])
    monkeypatch.setattr(turn_meta, "ensure_verified_plan_sync", lambda folder: (calls.append("verified"), False)[1])

    _write(tmp_path, _legacy_run())
    turn_meta.ensure_session_plan_pipeline(tmp_path)
    assert calls == ["consensus", "verified"]


# --- CLARIFY wait --------------------------------------------------------


def _route(folder, run, body):
    from agent_lab.room.turn_flow_phases import prepare_turn_routing_phase

    return prepare_turn_routing_phase(
        folder=folder,
        run_meta=run,
        plan_md="",
        body=body,
        active_agents=["cursor"],
        mention_targets=None,
        synthesize=False,
        consensus_mode=False,
        parallel_rounds=1,
        turn_profile=None,
        review_mode=False,
        human_turn_index=0,
        human_turn_num=1,
        efficiency_mode=False,
        research_mode=False,
        on_event=None,
        is_new_session=True,
    )


VAGUE_TOPIC = "앱"


@pytest.fixture()
def clarifier_on(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_INTERVIEW", "1")


def test_vague_topic_still_clarifies_on_an_existing_session(tmp_path, clarifier_on):
    """Fixture guard — without this the idea-lane assertion below has no teeth."""
    run = _legacy_run()
    _write(tmp_path, run)
    assert _route(tmp_path, run, VAGUE_TOPIC).clarifier_questions


@pytest.mark.parametrize("stage", [ideation.STAGE_EXPLORE, ideation.STAGE_SHAPE])
def test_vague_topic_does_not_wait_on_a_clarify_question(tmp_path, clarifier_on, stage):
    """A vague concept is the normal input here — propose under assumptions instead."""
    run = _ideation_run(stage)
    _write(tmp_path, run)
    result = _route(tmp_path, run, VAGUE_TOPIC)

    assert result.clarifier_questions is None
    assert "plan_workflow" not in result.run_meta


def test_clarify_resumes_at_plan_stage(tmp_path, clarifier_on):
    run = _ideation_run(ideation.STAGE_PLAN)
    _write(tmp_path, run)
    assert _route(tmp_path, run, VAGUE_TOPIC).clarifier_questions
