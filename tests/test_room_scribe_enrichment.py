"""Scribe enrichment and E2b policy."""

from __future__ import annotations

from agent_lab.room_objections import append_objection
from agent_lab.room_scribe_enrichment import (
    agent_contributions_section,
    build_scribe_enrichment,
    extract_agent_turn_summaries,
    format_scribe_agent_summaries_block,
    patch_plan_objections_only,
    should_skip_scribe_for_open_objections,
)


class _Msg:
    def __init__(self, role, agent=None, content=""):
        self.role = role
        self.agent = agent
        self.content = content


def test_scribe_enrichment_includes_block_and_contributions():
    meta: dict = {}
    append_objection(
        meta,
        from_agent="claude",
        act="BLOCK",
        body="bad ratio",
        human_turn=1,
        refs=["plan_action:1"],
    )
    msgs = [
        _Msg("user", content="go"),
        _Msg("agent", agent="codex", content="check files first"),
    ]
    text = build_scribe_enrichment(meta, msgs)
    assert "plan action index" in text.lower() or "plan_action" in text
    assert "미해결 이의" in text
    assert "Codex" in text or "codex" in text


def test_e2b_skip_scribe_on_discuss_with_open_objections():
    meta: dict = {}
    append_objection(
        meta,
        from_agent="claude",
        act="BLOCK",
        body="wait",
        human_turn=1,
        refs=["1"],
    )
    assert should_skip_scribe_for_open_objections(meta, mode="discuss", synthesize=True)
    assert not should_skip_scribe_for_open_objections(meta, mode="plan", synthesize=True)


def test_patch_plan_objections_only():
    meta: dict = {}
    append_objection(
        meta,
        from_agent="codex",
        act="CHALLENGE",
        body="recheck",
        human_turn=2,
        refs=["t-abc1234567"],
    )
    out = patch_plan_objections_only("## 합의\n- x\n", meta)
    assert "## 미해결 이의" in out


def test_agent_contributions_section():
    msgs = [
        _Msg("user", content="q"),
        _Msg("agent", agent="claude", content="risk A"),
        _Msg("agent", agent="codex", content="fact B"),
    ]
    sec = agent_contributions_section(msgs)
    assert "Claude" in sec or "claude" in sec
    assert "Codex" in sec or "codex" in sec


def test_richer_contributions_multi_bullet():
    msgs = [
        _Msg("user", content="q"),
        _Msg(
            "agent",
            agent="codex",
            content="- claim one\n- claim two",
        ),
    ]
    sec = agent_contributions_section(msgs)
    assert "claim one" in sec
    assert "claim two" in sec


def test_format_scribe_summaries_omits_verbatim_wall():
    body = "y" * 1500
    msgs = [
        _Msg("user", content="q"),
        _Msg("agent", agent="claude", content=body),
    ]
    block = format_scribe_agent_summaries_block(msgs)
    assert "Full verbatim" in block
    assert "y" * 400 not in block
    rows = extract_agent_turn_summaries(msgs)
    assert len(rows) == 1
