"""C9 — TurnPolicy FSM advance bypasses legacy synthesize gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.plan.workflow import (
    get_plan_workflow,
    init_plan_workflow_on_plan_send,
    orchestrate_plan_workflow_pipeline,
    plan_workflow_phase,
    set_plan_workflow_phase,
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


def test_orchestrate_pipeline_advances_draft_when_turn_policy_on_and_synthesize_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a live dogfood run found plan_workflow permanently stuck in DRAFT.

    ``orchestrate_plan_workflow_pipeline`` is invoked with ``synthesize=False``
    whenever the caller (``apply_turn_effects``) already decided
    ``advance_plan_workflow=True`` via TurnPolicy — the common case. Its internal
    ``tick_plan_workflow_after_turn`` calls didn't pass ``turn_policy_advance``,
    so they hit the legacy ``discuss_only`` short-circuit and never advanced
    past DRAFT, no matter how many turns ran.
    """
    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "0")

    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    set_plan_workflow_phase(folder, "DRAFT")
    plan_before = ""
    plan_md = (
        "# plan\n\n## 지금 실행\n\n"
        "1. fix typo\n"
        "   - 무엇을: `roompy` typo\n"
        "   - 어디서: `docs/_dogfood/x2-lift.md`\n"
        "   - 검증: `grep room.py docs/_dogfood/x2-lift.md`\n"
    )
    (folder / "plan.md").write_text(plan_md, encoding="utf-8")

    def _fake_peer_review(_folder, *_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "agent_lab.plan.workflow.run_plan_peer_review_round",
        _fake_peer_review,
    )

    run_meta = read_run_meta(folder)
    run_meta["_session_folder"] = str(folder)
    result_plan_md, _replies, tick = orchestrate_plan_workflow_pipeline(
        folder,
        topic="fix typo",
        messages=[],
        plan_md=plan_md,
        plan_before=plan_before,
        synthesize=False,
        cancelled=False,
        agents=["claude", "codex", "cursor"],
        permissions={},
        run_meta=run_meta,
    )

    pw = get_plan_workflow(read_run_meta(folder))
    assert pw["phase"] == "HUMAN_PENDING"
    assert tick.get("pending_approval") is True
    assert result_plan_md.strip() == plan_md.strip()


def test_post_agent_turn_plan_threads_active_agents_into_routing_contract_roster_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a live F7 dogfood session found the persisted turn_policy.routing_contract
    misclassified a 2-agent turn as fast_turn/roster_size=0. ``_post_agent_turn_plan``
    (the last writer that actually persists to run.json) built TurnSignals without
    passing roster_size, even though ``active_agents`` was right there as a parameter —
    the classmethod's ``run_meta["agents"]`` fallback found nothing at this point in the
    pipeline, so is_fast_turn's roster_size>1 guard never fired and the trace/eval-facing
    routing_contract snapshot was corrupted (actual turn behavior was unaffected, since
    role assignment reads the signal earlier, before this stamp)."""
    from agent_lab.room.turn_flow_plan import _post_agent_turn_plan

    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    run_meta = read_run_meta(folder)

    _plan_md, _scribe_applied, result_run_meta, _trigger = _post_agent_turn_plan(
        folder,
        topic="architecture standard 토픽 — roster 신호 확인용",
        messages=[],
        run_meta=run_meta,
        plan_before="",
        mode="discuss",
        synthesize=False,
        cancelled=False,
        active_agents=["claude", "codex"],
        permissions=None,
        on_event=None,
        consensus_meta=None,
        human_turn_num=1,
    )

    routing_contract = (result_run_meta.get("turn_policy") or {}).get("routing_contract") or {}
    assert routing_contract.get("roster_size") == 2
