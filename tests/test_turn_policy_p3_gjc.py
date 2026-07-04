"""P3 — GJC-style clarity/execute migration (skill-first plan FSM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.plan.workflow import (
    ensure_plan_clarify_interview,
    init_plan_workflow_on_plan_send,
    mcp_advance_plan_workflow_phase,
    mcp_run_clarity_interview,
    plan_fsm_skill_first_enabled,
    plan_workflow_phase,
    tick_plan_workflow_after_turn,
)
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


def test_plan_fsm_skill_first_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", raising=False)
    assert plan_fsm_skill_first_enabled() is True


def test_plan_fsm_skill_first_explicit_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "0")
    assert plan_fsm_skill_first_enabled() is False


def test_skill_first_tick_holds_clarify_without_auto_advance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    patch_run_meta(
        folder,
        lambda r: {
            **r,
            "verified_loop": {
                **(r.get("verified_loop") or {}),
                "loop_goal": {"text": "make the whole thing better somehow"},
            },
        },
    )

    tick = tick_plan_workflow_after_turn(
        folder,
        synthesize=False,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
        turn_policy_advance=True,
    )
    assert tick.get("skill_first_hold") is True
    assert tick.get("advance") is None
    assert plan_workflow_phase(read_run_meta(folder)) == "CLARIFY"


def test_skill_first_clarity_met_advances_without_mcp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    _seed_clarity_gate_goal(folder)

    tick = tick_plan_workflow_after_turn(
        folder,
        synthesize=False,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
        turn_policy_advance=True,
    )
    assert tick.get("skill_first_clarity_met") is True
    assert tick.get("advance") == "DRAFT"
    assert plan_workflow_phase(read_run_meta(folder)) == "DRAFT"


def test_skill_first_mcp_advance_to_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "1")
    monkeypatch.setenv("AGENT_LAB_INBOX_CALLER_AGENT", "codex")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    patch_run_meta(
        folder,
        lambda r: {**r, "room_preset": "supervisor", "agents": ["codex", "claude"]},
    )

    out = mcp_advance_plan_workflow_phase(
        folder,
        target_phase="DRAFT",
        caller_agent="codex",
        reason="clarity met via MCP",
    )
    assert out["ok"] is True
    assert plan_workflow_phase(read_run_meta(folder)) == "DRAFT"


def test_skill_first_cap_fallback_advances(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    _seed_clarity_gate_goal(folder)

    def _exhaust_cap(run: dict) -> dict:
        pw = run.get("plan_workflow") or {}
        pw["clarify_round"] = 3
        run["plan_workflow"] = pw
        return run

    patch_run_meta(folder, _exhaust_cap)

    tick = tick_plan_workflow_after_turn(
        folder,
        synthesize=False,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
        turn_policy_advance=True,
    )
    assert tick.get("skill_first_cap_fallback") is True
    assert tick.get("advance") == "DRAFT"
    assert plan_workflow_phase(read_run_meta(folder)) == "DRAFT"


def test_ensure_plan_clarify_interview_skipped_when_skill_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "1")
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER_ENGINE", "1")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    _seed_clarity_gate_goal(folder)
    patch_run_meta(folder, lambda r: {**r, "room_preset": "supervisor"})

    assert ensure_plan_clarify_interview(folder) is None


def test_mcp_run_clarity_interview_returns_panel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_INBOX_CALLER_AGENT", "codex")
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    _seed_clarity_gate_goal(folder)
    patch_run_meta(
        folder,
        lambda r: {**r, "room_preset": "supervisor", "agents": ["codex", "claude"]},
    )

    out = mcp_run_clarity_interview(folder, caller_agent="codex")
    assert out["ok"] is True
    panel = out["clarity_panel"]
    assert "dimensions" in panel
    assert set(panel["dimensions"]) >= {"goal", "constraints", "criteria", "context"}


def test_execute_propose_alias_stamps_skill_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.inbox.mcp_server import execute_propose

    monkeypatch.setenv("AGENT_LAB_TURN_POLICY", "1")
    monkeypatch.setenv("AGENT_LAB_INBOX_CALLER_AGENT", "cursor")
    monkeypatch.setenv("AGENT_LAB_SESSION_FOLDER", str(tmp_path / "sess"))
    folder = tmp_path / "sess"
    folder.mkdir()
    from agent_lab.run.meta import write_run_meta

    write_run_meta(folder, {"team_lead": "cursor", "agents": ["cursor"]})
    monkeypatch.setattr(
        "agent_lab.human_inbox.wait_for_inbox_item",
        lambda *_args, **_kwargs: {"decision": "defer", "status": "timeout"},
    )

    execute_propose(summary="ship feature", action_ref="action-1")
    assert read_run_meta(folder).get("_pending_skill_intent") == "propose_build"
