from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.room.turn_policy import (
    TurnPolicyEngine,
    TurnSignals,
    apply_turn_effects,
    detect_plan_execute_intent,
    maybe_stamp_plan_execute_skill_intent,
    resolve_discuss_light,
    turn_policy_enabled,
)


def test_fast_casual_send_no_scribe_despite_auto_plan_scribe_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "1")
    effects = TurnPolicyEngine.resolve(
        TurnSignals(room_preset="fast"),
    )
    assert effects.run_scribe is False
    assert effects.scribe_trigger == "none"
    assert effects.init_plan_workflow is False


def test_consensus_reached_without_pending_agreements_no_scribe() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            consensus_status="reached",
            pending_agreement_count=0,
        ),
    )
    assert effects.run_scribe is False
    assert effects.scribe_trigger == "none"


def test_consensus_reached_with_pending_agreements_scribes() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            consensus_status="reached",
            pending_agreement_count=2,
        ),
    )
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "consensus_reached"


def test_verified_loop_done_scribe_trigger() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(room_preset="supervisor", verified_loop_done=True),
    )
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "verified_loop_done"


def test_supervisor_casual_send_no_scribe() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            plan_workflow_active=True,
            plan_workflow_phase="CLARIFY",
        ),
    )
    assert effects.run_scribe is False
    assert effects.scribe_trigger == "none"


def test_skill_intent_plan_opens_scribe_in_clarify() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            plan_workflow_active=True,
            plan_workflow_phase="CLARIFY",
            skill_intent="plan",
        ),
    )
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "skill_intent"


def test_skill_intent_ignored_on_fast_preset() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(room_preset="fast", skill_intent="plan"),
    )
    assert effects.run_scribe is False
    assert effects.scribe_trigger == "none"


def test_pop_pending_skill_intent(tmp_path: Path) -> None:
    from agent_lab.room.turn_policy import pop_pending_skill_intent
    from agent_lab.run.meta import read_run_meta, write_run_meta

    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {"_pending_skill_intent": "plan"})
    run_meta = read_run_meta(folder)
    assert pop_pending_skill_intent(folder, run_meta) == "plan"
    assert "_pending_skill_intent" not in read_run_meta(folder)


def test_supervisor_first_turn_inits_plan_workflow_no_scribe() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            supervisor_first_turn=True,
            plan_workflow_active=False,
            plan_workflow_phase="INTAKE",
        ),
    )
    assert effects.init_plan_workflow is True
    assert effects.advance_plan_workflow is True
    assert effects.run_scribe is False


def test_supervisor_quick_category_skips_fsm_bootstrap() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            supervisor_first_turn=True,
            plan_workflow_active=False,
            plan_workflow_phase="INTAKE",
            route_category="quick",
        ),
    )
    assert effects.init_plan_workflow is False
    assert effects.advance_plan_workflow is False


def test_supervisor_discuss_light_skips_fsm_bootstrap() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            supervisor_first_turn=True,
            discuss_light=True,
        ),
    )
    assert effects.init_plan_workflow is False
    assert effects.advance_plan_workflow is False


EXECUTE_TOPIC = "docs 오타 1건 수정 plan action을 만들어 dry-run 승인 merge Oracle PASS까지"

DOGFOOD_EXECUTE_TOPIC = (
    "Makefile x2-lift-dogfood-env echo 갱신 + tests/test_ui_handoff_scenarios.py 수정\n"
    "검증: pytest tests/test_ui_handoff_scenarios.py -q\n"
    "dry-run 승인 후 merge, Oracle PASS까지."
)


def test_detect_plan_execute_intent_docs_typo_topic() -> None:
    assert detect_plan_execute_intent(EXECUTE_TOPIC) is True
    assert detect_plan_execute_intent("room.py에서 consensus 라운드 cap 기본값이 뭐야?") is False


def test_resolve_discuss_light_s1_topic_stays_light() -> None:
    assert (
        resolve_discuss_light(
            mode="discuss",
            synthesize=False,
            consensus_mode=False,
            agent_rounds=1,
            room_preset="supervisor",
            turn_profile="loop",
            topic="room.py에서 consensus 라운드 cap 기본값이 뭐야?",
        )
        is True
    )


def test_resolve_discuss_light_execute_intent_off() -> None:
    assert not resolve_discuss_light(
        mode="discuss",
        synthesize=False,
        consensus_mode=False,
        agent_rounds=1,
        room_preset="supervisor",
        turn_profile="loop",
        topic=EXECUTE_TOPIC,
    )


def test_resolve_discuss_light_followup_go_stays_off_when_session_execute() -> None:
    assert not resolve_discuss_light(
        mode="discuss",
        synthesize=False,
        consensus_mode=False,
        agent_rounds=1,
        room_preset="supervisor",
        turn_profile="loop",
        topic="GO",
        run_meta={"topic": EXECUTE_TOPIC},
    )


def test_resolve_discuss_light_active_plan_workflow_off() -> None:
    assert not resolve_discuss_light(
        mode="discuss",
        synthesize=False,
        consensus_mode=False,
        agent_rounds=1,
        room_preset="supervisor",
        turn_profile="loop",
        topic="casual question",
        run_meta={"plan_workflow": {"enabled": True, "phase": "DRAFT"}},
    )


def test_maybe_stamp_plan_execute_skill_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    run: dict[str, object] = {}
    maybe_stamp_plan_execute_skill_intent(run, topic=EXECUTE_TOPIC)
    assert run.get("_pending_skill_intent") == "plan"


def test_execute_intent_discuss_light_allows_fsm_bootstrap() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            supervisor_first_turn=True,
            discuss_light=False,
            skill_intent="plan",
        ),
    )
    assert effects.init_plan_workflow is True
    assert effects.advance_plan_workflow is True


def test_supervisor_anchored_topic_skips_fsm_bootstrap() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            supervisor_first_turn=True,
            clarity_short_circuit=True,
        ),
    )
    assert effects.init_plan_workflow is False
    assert effects.advance_plan_workflow is False


def test_execute_intent_clarity_short_circuit_allows_fsm_bootstrap() -> None:
    """Anchored dogfood execute topics must not short-circuit plan FSM (P0-5)."""
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            supervisor_first_turn=True,
            clarity_short_circuit=True,
            plan_execute_intent=True,
        ),
    )
    assert effects.init_plan_workflow is True
    assert effects.advance_plan_workflow is True


def test_from_run_meta_sets_plan_execute_intent_from_topic() -> None:
    signals = TurnSignals.from_run_meta(
        {"room_preset": "supervisor"},
        topic=DOGFOOD_EXECUTE_TOPIC,
    )
    assert signals.plan_execute_intent is True
    assert signals.clarity_short_circuit is True
    assert signals.routing_contract_snapshot()["skip_fsm_bootstrap"] is False


def test_quick_route_execute_intent_still_boots_fsm() -> None:
    """Keyword quick route (e.g. 오타) must not skip FSM on execute-intent topics."""
    signals = TurnSignals.from_run_meta(
        {"room_preset": "supervisor", "agents": ["cursor", "codex", "claude"]},
        topic=EXECUTE_TOPIC,
        roster_size=3,
        supervisor_first_turn=True,
    )
    assert signals.route_category == "quick"
    assert signals.plan_execute_intent is True
    assert signals.routing_contract_snapshot()["skip_fsm_bootstrap"] is False
    effects = TurnPolicyEngine.resolve(signals)
    assert effects.init_plan_workflow is True


def test_skill_intent_overrides_fsm_skip() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            supervisor_first_turn=True,
            route_category="quick",
            discuss_light=True,
            clarity_short_circuit=True,
            skill_intent="plan",
        ),
    )
    assert effects.init_plan_workflow is True
    assert effects.advance_plan_workflow is True


def test_turn_signals_from_run_meta_reads_routing_and_clarity() -> None:
    topic = "room.py에서 consensus 라운드 cap 기본값이 뭐야?"
    signals = TurnSignals.from_run_meta(
        {"room_preset": "supervisor", "discuss_light": True},
        topic=topic,
        supervisor_first_turn=True,
    )
    assert signals.route_category in {"quick", "standard"}
    assert signals.discuss_light is True
    assert signals.clarity_short_circuit is True


def test_prepare_turn_policy_s1_topic_skips_fsm_init(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.plan.workflow import is_plan_workflow_active
    from agent_lab.room.turn_policy import prepare_turn_policy_before_agent_round
    from agent_lab.run.meta import read_run_meta

    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    run_meta = read_run_meta(folder)
    run_meta["room_preset"] = "supervisor"
    run_meta["discuss_light"] = True

    topic = "room.py에서 consensus 라운드 cap 기본값이 뭐야?"
    run_meta, effects = prepare_turn_policy_before_agent_round(
        folder,
        run_meta,
        human_turn=1,
        topic=topic,
    )
    assert effects is not None
    assert effects.init_plan_workflow is False
    assert effects.advance_plan_workflow is False
    assert not is_plan_workflow_active(run_meta)


def test_supervisor_draft_phase_scribes() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            plan_workflow_active=True,
            plan_workflow_phase="DRAFT",
        ),
    )
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "plan_workflow_draft"
    assert effects.advance_plan_workflow is True


def test_human_pending_no_scribe() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            plan_workflow_active=True,
            plan_workflow_phase="HUMAN_PENDING",
        ),
    )
    assert effects.run_scribe is False
    assert effects.scribe_trigger == "none"


def test_synthesize_only_no_agent_round() -> None:
    effects = TurnPolicyEngine.resolve(TurnSignals(synthesize_only=True))
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "synthesize_only"
    assert effects.run_agent_round is False
    assert effects.turn_kind == "plan_side_effect"


def test_fast_synthesize_only_still_scribes() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(room_preset="fast", synthesize_only=True),
    )
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "synthesize_only"


def test_verified_loop_wins_over_consensus_pending() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            verified_loop_done=True,
            consensus_status="reached",
            pending_agreement_count=3,
        ),
    )
    assert effects.scribe_trigger == "verified_loop_done"


def test_assign_task_owners_on_consensus_mode() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(room_preset="fast", consensus_mode=True),
    )
    assert effects.assign_task_owners is True
    assert effects.run_scribe is False


def test_turn_signals_from_run_meta_pending_count() -> None:
    run_meta = {
        "room_preset": "supervisor",
        "consensus_agreements": [
            {"excerpt": "topic A", "plan_synced": False},
            {"excerpt": "done", "plan_synced": True},
        ],
    }
    signals = TurnSignals.from_run_meta(run_meta, consensus_meta={"status": "reached"})
    assert signals.pending_agreement_count == 1
    assert signals.consensus_status == "reached"


def test_apply_turn_effects_disabled_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "0")
    assert turn_policy_enabled() is False
    result = apply_turn_effects(signals=TurnSignals(room_preset="fast"))
    assert result.applied is False
    assert result.detail == "turn_policy_disabled"


def test_apply_turn_effects_applies_when_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    assert turn_policy_enabled() is True
    result = apply_turn_effects(
        signals=TurnSignals(
            room_preset="supervisor",
            consensus_status="reached",
            pending_agreement_count=1,
        ),
    )
    assert result.applied is True
    assert result.detail == "no_session_folder"
    assert result.effects.run_scribe is True


def test_turn_effects_to_turn_policy_dict() -> None:
    effects = TurnPolicyEngine.resolve(TurnSignals(synthesize_only=True))
    payload = effects.to_turn_policy_dict()
    assert payload["scribe_trigger"] == "synthesize_only"
    assert payload["turn_kind"] == "plan_side_effect"


def test_build_turn_policy_record_includes_routing_contract() -> None:
    from agent_lab.room.turn_policy import build_turn_policy_record

    signals = TurnSignals(
        room_preset="supervisor",
        supervisor_first_turn=True,
        route_category="standard",
        discuss_light=True,
        clarity_short_circuit=True,
    )
    effects = TurnPolicyEngine.resolve(signals)
    payload = build_turn_policy_record(effects, signals)
    assert payload["init_plan_workflow"] is False
    assert payload["routing_contract"] == {
        "route_category": "standard",
        "discuss_light": True,
        "clarity_short_circuit": True,
        "plan_execute_intent": False,
        "skip_fsm_bootstrap": True,
        "fast_turn": False,
        "supervisor_turn": True,
        "roster_size": 0,
    }


def test_prepare_turn_policy_persists_routing_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.room.turn_policy import prepare_turn_policy_before_agent_round
    from agent_lab.run.meta import read_run_meta

    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    run_meta = read_run_meta(folder)
    run_meta["room_preset"] = "supervisor"
    run_meta["discuss_light"] = True

    topic = "room.py에서 consensus 라운드 cap 기본값이 뭐야?"
    run_meta, _effects = prepare_turn_policy_before_agent_round(
        folder,
        run_meta,
        human_turn=1,
        topic=topic,
    )
    tp = read_run_meta(folder).get("turn_policy")
    assert isinstance(tp, dict)
    contract = tp.get("routing_contract")
    assert isinstance(contract, dict)
    assert contract.get("clarity_short_circuit") is True
    assert contract.get("skip_fsm_bootstrap") is True
    assert tp.get("init_plan_workflow") is False


def test_turn_policy_default_on_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_TURN_POLICY", raising=False)
    assert turn_policy_enabled() is True


def test_effective_permissions_skips_discuss_overlay_when_turn_policy_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.room.messages import effective_agent_permissions

    base = {"claude": {"write": True}, "codex": {"cli": False}}
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "0")
    legacy = effective_agent_permissions(base, topic="t", plan_md="", run_meta={})
    assert legacy.get("_discuss_mode") is True
    assert legacy.get("claude", {}).get("write") is False

    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    tp = effective_agent_permissions(base, topic="t", plan_md="", run_meta={})
    assert "_discuss_mode" not in tp
    assert tp.get("claude", {}).get("write") is True


def test_assign_task_owners_from_run_meta_snapshot() -> None:
    from agent_lab.room.turn_policy import assign_task_owners_from_run_meta

    assert assign_task_owners_from_run_meta(None) is None
    assert assign_task_owners_from_run_meta({}) is None
    assert assign_task_owners_from_run_meta({"turn_policy": {}}) is None
    assert assign_task_owners_from_run_meta({"turn_policy": {"assign_task_owners": True}}) is True
    assert assign_task_owners_from_run_meta({"turn_policy": {"assign_task_owners": False}}) is False


def test_prepare_turn_policy_second_turn_does_not_init_fsm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Casual supervisor send on turn 2 must not bootstrap FSM from synthesize hint."""
    from agent_lab.plan.workflow import is_plan_workflow_active
    from agent_lab.room.turn_policy import prepare_turn_policy_before_agent_round
    from agent_lab.run.meta import read_run_meta

    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    run_meta = read_run_meta(folder)
    run_meta["room_preset"] = "supervisor"

    run_meta, effects = prepare_turn_policy_before_agent_round(
        folder,
        run_meta,
        human_turn=2,
    )
    assert effects is not None
    assert effects.init_plan_workflow is False
    assert not is_plan_workflow_active(run_meta)


def test_prepare_turn_policy_supervisor_first_turn_inits_fsm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.plan.workflow import is_plan_workflow_active, plan_workflow_phase
    from agent_lab.room.turn_policy import prepare_turn_policy_before_agent_round
    from agent_lab.run.meta import read_run_meta

    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    run_meta = read_run_meta(folder)
    run_meta["room_preset"] = "supervisor"

    run_meta, effects = prepare_turn_policy_before_agent_round(
        folder,
        run_meta,
        human_turn=1,
    )
    assert effects is not None
    assert is_plan_workflow_active(run_meta)
    assert plan_workflow_phase(run_meta) == "CLARIFY"
    assert effects.init_plan_workflow is False
    assert effects.advance_plan_workflow is True
    assert run_meta.get("turn_policy", {}).get("assign_task_owners") is False
    persisted = read_run_meta(folder)
    assert isinstance(persisted.get("turn_policy"), dict)
    assert persisted.get("room_preset") == "supervisor"


def test_prepare_turn_policy_preserves_skill_after_fsm_init(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """read_run_meta after FSM init must not drop pending/active skill intent."""
    from agent_lab.plan.workflow import is_plan_workflow_active, plan_workflow_phase
    from agent_lab.room.turn_policy import (
        pop_pending_skill_intent,
        prepare_turn_policy_before_agent_round,
        stamp_active_skill_intent,
    )
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    patch_run_meta(
        folder,
        lambda run: (
            run.update(
                {
                    "room_preset": "supervisor",
                    "topic": DOGFOOD_EXECUTE_TOPIC,
                    "agents": ["cursor", "codex", "claude"],
                    "_pending_skill_intent": "plan",
                }
            )
            or run
        ),
    )
    run_meta = read_run_meta(folder)
    stamp_active_skill_intent(run_meta, pop_pending_skill_intent(folder, run_meta))

    run_meta, effects = prepare_turn_policy_before_agent_round(
        folder,
        run_meta,
        human_turn=1,
        topic=DOGFOOD_EXECUTE_TOPIC,
    )
    assert effects is not None
    assert is_plan_workflow_active(run_meta)
    assert plan_workflow_phase(run_meta) == "CLARIFY"
    assert effects.init_plan_workflow is False
    assert effects.advance_plan_workflow is True
    assert effects.run_scribe is True
    tp = run_meta.get("turn_policy") or {}
    assert tp.get("routing_contract", {}).get("skip_fsm_bootstrap") is False


S1_TOPIC = "room.py에서 consensus 라운드 cap 기본값이 뭐야?"


def test_p2b_topic_only_trio_clarity_is_supervisor_not_fast() -> None:
    from agent_lab.room.turn_policy import is_fast_turn, is_supervisor_turn

    signals = TurnSignals(
        route_category="quick",
        clarity_short_circuit=True,
        roster_size=3,
    )
    assert is_fast_turn(signals) is False
    assert is_supervisor_turn(signals) is True
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            supervisor_first_turn=True,
            route_category="quick",
            clarity_short_circuit=True,
            roster_size=3,
        ),
    )
    assert effects.init_plan_workflow is False


def test_p2b_topic_only_single_quick_is_fast() -> None:
    from agent_lab.room.turn_policy import is_fast_turn, is_supervisor_turn

    signals = TurnSignals(route_category="quick", roster_size=1)
    assert is_fast_turn(signals) is True
    assert is_supervisor_turn(signals) is False
    effects = TurnPolicyEngine.resolve(signals)
    assert effects.init_plan_workflow is False
    assert effects.run_scribe is False


def test_p2b_preset_supervisor_wins_over_quick_route() -> None:
    from agent_lab.room.turn_policy import is_fast_turn

    signals = TurnSignals(
        room_preset="supervisor",
        route_category="quick",
        roster_size=1,
    )
    assert is_fast_turn(signals) is False


def test_p2b_routing_contract_snapshot_includes_turn_mode() -> None:
    signals = TurnSignals(
        route_category="quick",
        clarity_short_circuit=True,
        roster_size=3,
    )
    snap = signals.routing_contract_snapshot()
    assert snap["fast_turn"] is False
    assert snap["supervisor_turn"] is True
    assert snap["roster_size"] == 3


def test_p2b_from_run_meta_reads_roster_size() -> None:
    signals = TurnSignals.from_run_meta(
        {"agents": ["cursor", "codex", "claude"]},
        topic=S1_TOPIC,
    )
    assert signals.roster_size == 3
