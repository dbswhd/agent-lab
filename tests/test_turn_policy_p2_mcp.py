from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.room.messages import ChatMessage
from agent_lab.plan.workflow import (
    init_plan_workflow_on_plan_send,
    mcp_advance_plan_workflow_phase,
    plan_workflow_phase,
)
from agent_lab.room.turn_policy import (
    TurnPolicyEngine,
    TurnSignals,
    count_proposed_tags_in_turn,
    proposed_envelope_threshold,
)


def test_proposed_envelope_threshold_opens_scribe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PROPOSED_SKILL_INTENT_THRESHOLD", "2")
    assert proposed_envelope_threshold() == 2
    effects = TurnPolicyEngine.resolve(
        TurnSignals(
            room_preset="supervisor",
            plan_workflow_active=True,
            plan_workflow_phase="CLARIFY",
            proposed_tags_count=2,
        ),
    )
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "skill_intent"


def test_count_proposed_tags_in_turn_dedupes() -> None:
    messages = [
        ChatMessage(role="user", agent=None, content="go"),
        ChatMessage(role="agent", agent="codex", content="[PROPOSED: add tests]"),
        ChatMessage(role="agent", agent="claude", content="[PROPOSED: add tests] ok"),
        ChatMessage(role="agent", agent="cursor", content="[PROPOSED: wire MCP]"),
    ]
    assert count_proposed_tags_in_turn(messages) == 2


def test_propose_build_stamps_pending_skill_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.human_inbox import create_mcp_build_and_wait
    from agent_lab.run.meta import read_run_meta, write_run_meta

    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_INBOX_CALLER_AGENT", "cursor")
    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {"team_lead": "cursor", "agents": ["cursor"]})

    monkeypatch.setattr(
        "agent_lab.human_inbox.wait_for_inbox_item",
        lambda *_args, **_kwargs: {"decision": "defer", "status": "timeout"},
    )

    create_mcp_build_and_wait(
        folder,
        summary="implement feature",
        action_ref="action-1",
        caller_agent="cursor",
    )
    assert read_run_meta(folder).get("_pending_skill_intent") == "propose_build"


def test_propose_build_rejects_non_lead(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.human_inbox import create_mcp_build_and_wait
    from agent_lab.run.meta import write_run_meta

    monkeypatch.setenv("AGENT_LAB_INBOX_CALLER_AGENT", "codex")
    folder = tmp_path / "sess"
    folder.mkdir()
    write_run_meta(folder, {"team_lead": "cursor", "agents": ["cursor", "codex"]})

    with pytest.raises(ValueError, match="team lead"):
        create_mcp_build_and_wait(
            folder,
            summary="implement",
            action_ref="a1",
            caller_agent="codex",
        )


def test_mcp_advance_plan_workflow_forward_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    monkeypatch.setenv("AGENT_LAB_INBOX_CALLER_AGENT", "codex")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)

    def _roster(run: dict) -> dict:
        run["room_preset"] = "supervisor"
        run["agents"] = ["codex", "claude"]
        return run

    patch_run_meta(folder, _roster)
    assert plan_workflow_phase(read_run_meta(folder)) == "CLARIFY"

    out = mcp_advance_plan_workflow_phase(
        folder,
        target_phase="DRAFT",
        caller_agent="codex",
        reason="clarity met",
    )
    assert out["ok"] is True
    assert out["phase"] == "DRAFT"
    assert plan_workflow_phase(read_run_meta(folder)) == "DRAFT"

    with pytest.raises(ValueError, match="forward advance only"):
        mcp_advance_plan_workflow_phase(folder, target_phase="CLARIFY", caller_agent="codex")

    with pytest.raises(ValueError, match="target_phase must be one of"):
        mcp_advance_plan_workflow_phase(folder, target_phase="APPROVED", caller_agent="codex")


def test_skill_intent_propose_build_opens_scribe() -> None:
    effects = TurnPolicyEngine.resolve(
        TurnSignals(room_preset="supervisor", skill_intent="propose_build"),
    )
    assert effects.run_scribe is True
    assert effects.scribe_trigger == "skill_intent"
