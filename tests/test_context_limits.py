"""Context limits and enriched bundle meta."""

from __future__ import annotations

from dataclasses import dataclass

from agent_lab.context.bundle import build_context_bundle
from agent_lab.context.limits import agent_context_limits, trim_level
from agent_lab.context.meta import summarize_turn_context


@dataclass
class _Msg:
    role: str
    agent: str | None
    content: str
    parallel_round: int | None = None


def _format_thread(topic: str, messages: list[_Msg]) -> str:
    return f"TOPIC:{topic}\nMSGS:{len(messages)}"


def test_enriched_meta_has_budget_and_trim():
    msgs = [_Msg("user", None, "hello"), _Msg("agent", "codex", "reply", 1)]
    bundle = build_context_bundle(
        "topic",
        msgs,
        "cursor",
        all_messages=msgs,
    )
    m = bundle.meta
    assert m.budget_pct >= 0
    assert m.trim_level in ("ok", "warn", "critical")
    assert m.limits.get("max_thread_chars") == agent_context_limits().max_thread_chars
    assert m.messages_in_session == 2
    d = m.to_dict()
    assert "layer_chars" in d and "budget_pct" in d


def test_trim_level_thresholds():
    lim = agent_context_limits()
    assert trim_level(budget_pct=50, turns_omitted=0, chars_omitted=0, limits=lim) == "ok"
    assert (
        trim_level(
            budget_pct=lim.warn_budget_pct,
            turns_omitted=1,
            chars_omitted=0,
            limits=lim,
        )
        == "warn"
    )
    assert (
        trim_level(
            budget_pct=lim.critical_budget_pct,
            turns_omitted=0,
            chars_omitted=0,
            limits=lim,
        )
        == "critical"
    )


def test_summarize_turn_context():
    agents = [
        {"trim_level": "warn", "layer_chars": {"total": 1000}},
        {"trim_level": "ok", "layer_chars": {"total": 500}},
    ]
    s = summarize_turn_context(agents)
    assert s["trim_level"] == "warn"
    assert s["payload_chars_max"] == 1000
    assert s["agent_count"] == 2
