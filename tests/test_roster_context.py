"""Active roster context blocks for model-flexible room sessions."""

from __future__ import annotations

from agent_lab.room.roster_context import (
    active_agents_from_run_meta,
    build_active_roster_block,
    build_multi_agent_coordination,
    build_peer_decision_guidance,
    delegator_persona,
    inactive_known_agents,
    review_round2_order,
)
from agent_lab.role_plan import persona_for_agent


def test_active_roster_from_run_meta_agents():
    meta = {"agents": ["cursor", "claude"], "team_lead": "cursor"}
    assert active_agents_from_run_meta(meta) == ["cursor", "claude"]


def test_active_roster_block_marks_codex_off():
    block = build_active_roster_block(["cursor", "claude"], team_lead="cursor")
    assert "In room" in block
    assert "cursor" in block.lower() or "Cursor" in block
    assert "Not in room" in block
    assert "Codex" in block
    assert "MESSAGE" in block


def test_multi_agent_coordination_excludes_absent():
    block = build_multi_agent_coordination(["cursor", "claude"])
    assert "not" in block.lower() or "Not" in block
    assert "Codex" in block


def test_delegator_persona_no_codex_when_absent():
    text = delegator_persona(["cursor", "claude"])
    assert "Off this session" in text
    assert "Codex" in text
    assert "execute/patch" in text
    assert "blind-spot review" in text
    assert "MESSAGE" in text


def test_delegator_role_uses_dynamic_persona():
    meta = {"agents": ["cursor", "claude"]}
    text = persona_for_agent({"cursor": "delegator"}, "cursor", run_meta=meta)
    assert "Active peers" in text
    assert "Codex" in text


def test_inactive_known_agents():
    assert inactive_known_agents(["cursor", "claude"]) == ["codex", "kimi_work"]


def test_review_round2_order_classic():
    assert review_round2_order(["cursor", "codex", "claude"]) == [
        "claude",
        "codex",
        "cursor",
    ]


def test_review_round2_order_includes_kimi_work():
    assert review_round2_order(["cursor", "claude", "kimi_work"]) == [
        "claude",
        "kimi_work",
        "cursor",
    ]


def test_review_round2_order_without_claude():
    assert review_round2_order(["cursor", "codex", "kimi_work"]) == [
        "kimi_work",
        "codex",
        "cursor",
    ]
