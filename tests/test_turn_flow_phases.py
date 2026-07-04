"""Unit tests for turn_flow_phases consensus/harvest helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.room.messages import ChatMessage
from agent_lab.room.turn_flow_phases import (
    ConsensusPhaseResult,
    build_turn_body,
    prepare_turn_routing_phase,
    run_consensus_phase,
)


def test_prepare_turn_routing_direct_mention_disables_consensus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agent_lab.room.turn_flow_phases.direct_turn_for_mention_targets",
        lambda _targets: True,
    )
    monkeypatch.setattr(
        "agent_lab.room.team_orchestration.resolve_turn_lead",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "agent_lab.room.turn_flow_phases._resolve_stage_routing",
        lambda *args, **kwargs: kwargs.get("consensus_mode", False),
    )
    monkeypatch.setattr(
        "agent_lab.room.turn_flow_phases._set_active_turn_flags",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "agent_lab.room.turn_flow_phases.ensure_adaptive_efficiency_for_turn",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "agent_lab.room.turn_flow_phases.apply_turn_profile_flags",
        lambda *args, **kwargs: kwargs.get("parallel_rounds", 1),
    )
    monkeypatch.setattr(
        "agent_lab.room.turn_flow_phases.prepare_clarifier_for_turn",
        lambda *args, **kwargs: None,
    )

    result = prepare_turn_routing_phase(
        folder=None,
        run_meta={},
        plan_md="",
        body="hi",
        active_agents=[],
        mention_targets=["cursor"],
        synthesize=False,
        consensus_mode=True,
        parallel_rounds=2,
        turn_profile=None,
        review_mode=False,
        human_turn_index=0,
        human_turn_num=1,
        efficiency_mode=False,
        research_mode=False,
        on_event=None,
        is_new_session=True,
    )
    assert result.consensus_mode is False
    assert result.mode == "discuss"


def test_build_turn_body_appends_attachment_block() -> None:
    assert build_turn_body("hello", "file.pdf") == "hello\n\n---\n\nfile.pdf"
    assert build_turn_body("", "file.pdf") == "file.pdf"


def test_run_consensus_phase_returns_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    messages = [ChatMessage(role="user", agent=None, content="hi")]
    run_meta: dict = {"agents": ["cursor"]}

    monkeypatch.setattr(
        "agent_lab.room.turn_flow_phases._prepare_team_coordination_before_round",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "agent_lab.room.turn_meta._try_delegate_turn",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "agent_lab.room.turn_flow_phases.run_turn_agent_rounds",
        lambda **kwargs: (
            [ChatMessage(role="agent", agent="cursor", content="ok")],
            {"status": "done"},
            1,
            False,
        ),
    )
    monkeypatch.setattr(
        "agent_lab.room.turn_flow_phases.after_agent_replies_checkpoint",
        lambda *args, **kwargs: None,
    )

    result = run_consensus_phase(
        topic="hi",
        messages=messages,
        folder=folder,
        body="hi",
        run_meta=run_meta,
        active_agents=["cursor"],  # type: ignore[arg-type]
        clarifier_questions=None,
        consensus_mode=False,
        parallel_rounds=1,
        on_event=None,
        permissions=None,
        human_turn_index=0,
        human_turn_num=1,
        plan_md="",
        context_log=[],
        efficiency_mode=False,
        review_mode=False,
        mode="discuss",
        synthesize=False,
    )

    assert isinstance(result, ConsensusPhaseResult)
    assert len(result.replies) == 1
    assert messages[-1].content == "ok"
