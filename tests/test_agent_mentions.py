"""@agent mention routing — target subset of active roster."""

from __future__ import annotations

from agent_lab.room.agent_mentions import (
    apply_agent_mention_filter,
    parse_agent_mentions,
    strip_agent_mentions,
)


def test_parse_single_agent_mention():
    pool = ["claude", "kimi_work"]
    assert parse_agent_mentions("@claude please review", pool) == ["claude"]


def test_parse_multiple_agent_mentions():
    pool = ["cursor", "claude", "kimi_work"]
    assert parse_agent_mentions("@claude @kimi_work sync on this", pool) == ["claude", "kimi_work"]


def test_mention_ignored_when_not_in_pool():
    pool = ["claude", "kimi_work"]
    assert parse_agent_mentions("@codex only me", pool) == []


def test_kimi_alias_prefers_kimi_work():
    pool = ["claude", "kimi_work"]
    assert parse_agent_mentions("@kimi check refs", pool) == ["kimi_work"]


def test_kimi_work_hyphen_alias():
    pool = ["claude", "kimi_work"]
    assert parse_agent_mentions("@kimi-work hello", pool) == ["kimi_work"]


def test_file_path_does_not_trigger_agent_filter():
    pool = ["claude", "kimi_work"]
    assert parse_agent_mentions("see @src/agent_lab/foo.py", pool) == []


def test_apply_filter_strips_mentions_from_body():
    pool = ["claude", "kimi_work"]
    agents, body, targets = apply_agent_mention_filter("@claude focus on token budget", pool)
    assert agents == ["claude"]
    assert body == "focus on token budget"
    assert targets == ["claude"]


def test_apply_filter_noop_without_mentions():
    pool = ["claude", "kimi_work"]
    agents, body, targets = apply_agent_mention_filter("everyone weigh in", pool)
    assert agents == pool
    assert body == "everyone weigh in"
    assert targets == []


def test_apply_filter_honors_mention_from_roster_when_not_active():
    pool = ["claude", "kimi_work"]
    agents, body, targets = apply_agent_mention_filter(
        "@claude Question 마저 올려봐",
        ["kimi_work"],
        roster_pool=pool,
    )
    assert agents == ["claude"]
    assert body == "Question 마저 올려봐"
    assert targets == ["claude"]


def test_strip_agent_mentions_only():
    assert strip_agent_mentions("@claude @kimi_work  hi") == "hi"


def test_apply_turn_agent_mentions_updates_message_and_run_meta():
    from agent_lab.room.turn_flow_support import apply_turn_agent_mentions

    run_meta: dict = {}
    body, agents, targets = apply_turn_agent_mentions(
        "@claude only you",
        ["claude", "kimi_work"],
        run_meta,
    )
    assert agents == ["claude"]
    assert body == "only you"
    assert targets == ["claude"]
    assert run_meta["_turn_target_agents"] == ["claude"]
    assert run_meta["agents"] == ["claude"]


def test_apply_turn_agent_mentions_uses_roster_pool():
    from agent_lab.room.turn_flow_support import apply_turn_agent_mentions

    run_meta: dict = {}
    body, agents, targets = apply_turn_agent_mentions(
        "@claude only you",
        ["kimi_work"],
        run_meta,
        roster_pool=["claude", "kimi_work"],
    )
    assert agents == ["claude"]
    assert body == "only you"
    assert targets == ["claude"]
    assert run_meta["_turn_target_agents"] == ["claude"]
    assert run_meta["agents"] == ["claude"]


def test_effective_invoke_agents_respects_turn_targets():
    from agent_lab.room.agent_mentions import effective_invoke_agents

    run_meta = {"_turn_target_agents": ["claude"]}
    assert effective_invoke_agents(
        ["claude", "kimi_work"],
        run_meta,
    ) == ["claude"]
    assert effective_invoke_agents(
        ["claude", "kimi_work"],
        {},
    ) == ["claude", "kimi_work"]
