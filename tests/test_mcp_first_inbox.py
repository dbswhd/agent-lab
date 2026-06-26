"""MCP-first Human Inbox — Phase C policy + Phase E MCP path tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.cursor_inbox_mcp import discuss_inbox_mcp_enabled
from agent_lab.human_inbox import (
    create_inbox_item,
    create_mcp_question_and_wait,
    has_pending_question,
)
from agent_lab.inbox_harvest import harvest_discuss_questions, orchestrator_inbox_harvest_enabled
from agent_lab.inbox_mcp_policy import inbox_gate_owner, mcp_first_inbox_policy_active
from agent_lab.run_meta import patch_run_meta, read_run_meta


def _supervisor_run(*, lead: str = "cursor") -> dict:
    return {
        "room_preset": "supervisor",
        "team_lead": lead,
        "agents": ["cursor", "codex", "claude"],
        "human_inbox": [],
    }


def test_mcp_first_policy_active_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", raising=False)
    assert mcp_first_inbox_policy_active() is True
    assert orchestrator_inbox_harvest_enabled() is False


def test_inbox_gate_owner_falls_back_from_cursor_lead() -> None:
    assert inbox_gate_owner(_supervisor_run()) == "codex"
    assert inbox_gate_owner(_supervisor_run(lead="codex")) == "codex"


def test_discuss_mcp_lead_only_under_mcp_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", raising=False)
    run = _supervisor_run()
    assert discuss_inbox_mcp_enabled(run, agent_id="codex") is True
    assert discuss_inbox_mcp_enabled(run, agent_id="claude") is False
    assert discuss_inbox_mcp_enabled(run, agent_id="cursor") is False


def test_discuss_mcp_disabled_when_legacy_harvest_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "1")
    run = _supervisor_run(lead="codex")
    assert discuss_inbox_mcp_enabled(run, agent_id="codex") is False
    assert discuss_inbox_mcp_enabled(run, agent_id="claude") is False


def test_single_flight_rejects_second_ask_human(tmp_path: Path) -> None:
    folder = tmp_path / "sess-mcp"
    folder.mkdir()
    (folder / "run.json").write_text('{"human_inbox": []}', encoding="utf-8")

    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "human_inbox": [
                {
                    "id": "q-pending",
                    "kind": "question",
                    "status": "pending",
                    "source": "mcp_ask_human",
                    "prompt": "first?",
                    "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="pending Human Inbox question"):
        create_mcp_question_and_wait(
            folder,
            question="second?",
            options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            caller_agent="codex",
            policy_lane="discuss",
        )


def test_non_lead_cannot_ask_on_discuss(tmp_path: Path) -> None:
    folder = tmp_path / "sess-lead"
    folder.mkdir()
    patch_run_meta(
        folder,
        lambda run: {
            **run,
            **_supervisor_run(lead="codex"),
        },
    )

    with pytest.raises(ValueError, match="only inbox gate owner"):
        create_mcp_question_and_wait(
            folder,
            question="scope?",
            options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            caller_agent="claude",
            policy_lane="discuss",
        )


def test_fast_lead_cursor_may_ask_human(tmp_path: Path) -> None:
    folder = tmp_path / "sess-fast-cursor"
    folder.mkdir()
    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "room_preset": "fast",
            "team_lead": "cursor",
            "agents": ["cursor"],
        },
    )

    from agent_lab.inbox_mcp_policy import enforce_mcp_ask_human_policy

    enforce_mcp_ask_human_policy(
        folder,
        caller_agent="cursor",
        policy_lane="discuss",
    )


def test_mcp_path_replaces_harvest_for_plan_open(tmp_path: Path) -> None:
    folder = tmp_path / "sess-path"
    folder.mkdir()
    run_meta = _supervisor_run()
    plan_md = "## 쟁점 / 미결정\n- cadence sweep scope"

    harvested = harvest_discuss_questions(
        run_meta,
        [],
        plan_md=plan_md,
        mode="discuss",
    )
    assert harvested == []

    patch_run_meta(folder, lambda run: {**run, **run_meta})
    item = create_inbox_item(
        folder,
        kind="question",
        source="mcp_ask_human",
        prompt="Plan OPEN: cadence sweep scope?",
        options=[
            {"id": "vu", "label": "VU only"},
            {"id": "both", "label": "VU + Theme"},
        ],
        trigger="T-Q2",
        context_ref="plan.md",
    )
    assert item["source"] == "mcp_ask_human"
    assert has_pending_question(read_run_meta(folder)) is True
