"""Unit tests for ContextBundle trim pin and peer dedupe."""

from __future__ import annotations

from dataclasses import dataclass

from agent_lab.context_bundle import build_context_bundle
from agent_lab.room_context import (
    collect_peer_messages,
    dedupe_peer_from_recent,
    pinned_current_turn_messages,
    prepare_recent_messages,
)


@dataclass
class _Msg:
    role: str
    agent: str | None
    content: str
    parallel_round: int | None = None


def _format_thread(topic: str, messages: list[_Msg]) -> str:
    lines = [f"Human topic:\n{topic}\n"]
    for m in messages:
        if m.role == "user":
            lines.append(f"Human:\n{m.content}\n")
        elif m.role == "agent" and m.agent:
            lines.append(f"{m.agent}:\n{m.content}\n")
    return "\n".join(lines)


def test_pinned_current_turn_keeps_human_under_char_trim():
    old = _Msg("user", None, "old turn question")
    old_a = _Msg("agent", "codex", "old answer" * 200, 1)
    human = _Msg("user", None, "latest question")
    a1 = _Msg("agent", "claude", "x" * 50000, 1)
    a2 = _Msg("agent", "codex", "y" * 50000, 1)
    messages = [old, old_a, human, a1, a2]
    trimmed, _, chars_om, pin_count = prepare_recent_messages(
        messages, max_turns=8, max_chars=80000
    )
    assert pin_count == 3
    assert human in trimmed
    assert a1 in trimmed
    assert a2 in trimmed
    assert chars_om >= 0


def test_peer_dedupe_removes_duplicate_agent_lines():
    human = _Msg("user", None, "q")
    r1_claude = _Msg("agent", "claude", "claude r1", 1)
    r1_codex = _Msg("agent", "codex", "codex r1", 1)
    messages = [human, r1_claude, r1_codex]
    peer = collect_peer_messages(messages, "cursor", 2)
    assert len(peer) == 2
    recent, removed = dedupe_peer_from_recent(messages, peer)
    assert removed == 2
    assert all(m.role != "agent" or m not in peer for m in recent)
    assert human in recent


def test_build_context_bundle_has_layers_and_meta():
    human = _Msg("user", None, "hello")
    messages = [human, _Msg("agent", "codex", "hi", 1)]
    bundle = build_context_bundle(
        "topic",
        messages,
        "cursor",
        format_thread=_format_thread,
    )
    text = bundle.render()
    assert "[고정 constraints]" in text
    assert "[plan 미결]" in text
    assert "[최근 N턴]" in text
    assert bundle.meta.layer_chars["total"] == len(text)


def test_r15_bridge_on_round2(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_R15", "1")
    human = _Msg("user", None, "q")
    messages = [
        human,
        _Msg("agent", "claude", "claude says alpha", 1),
        _Msg("agent", "codex", "codex says beta", 1),
    ]
    bundle = build_context_bundle(
        "topic",
        messages,
        "cursor",
        parallel_round=2,
        format_thread=_format_thread,
    )
    assert "[R1 요약 · bridge]" in bundle.render()
    assert bundle.meta.layer_chars.get("bridge", 0) > 0

