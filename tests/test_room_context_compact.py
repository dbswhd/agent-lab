"""Tests for AGENT_LAB_COMMS_COMPACT current-turn pin compaction."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import pytest

from agent_lab.room import context as rc


@dataclass
class _Msg:
    role: str
    content: str
    agent: str = ""
    parallel_round: int | None = None


def _make_turn(agent_replies: list[tuple[str, str]]) -> list[_Msg]:
    """Build [Human + agent replies] for one turn."""
    msgs = [_Msg(role="user", content="human prompt", agent="human")]
    for agent, text in agent_replies:
        msgs.append(_Msg(role="assistant", content=text, agent=agent))
    return msgs


class TestCompactCurrentTurnPins:
    def test_latest_per_agent_kept(self) -> None:
        msgs = _make_turn([
            ("claude", "first claude reply"),
            ("claude", "latest claude reply"),
            ("cursor", "cursor reply"),
        ])
        kept, dropped = rc.compact_current_turn_pins(msgs, max_chars=100_000)
        assert len(kept) == 3  # human + 2 latest per agent
        assert kept[1].content == "latest claude reply"
        assert kept[2].content == "cursor reply"
        assert dropped == 1

    def test_char_cap_drops_oldest(self) -> None:
        msgs = _make_turn([
            ("claude", "a" * 1000),
            ("cursor", "b" * 1000),
            ("codex", "c" * 1000),
        ])
        budget = 1500  # human + one 1000-char agent reply only
        kept, dropped = rc.compact_current_turn_pins(msgs, max_chars=budget)
        # Human always kept; at most one agent fits.
        assert kept[0].role == "user"
        assert len(kept) <= 2
        assert dropped >= 2

    def test_no_human_returns_original(self) -> None:
        msgs = [_Msg(role="assistant", content="only agents", agent="claude")]
        kept, dropped = rc.compact_current_turn_pins(msgs, max_chars=100_000)
        assert kept == msgs
        assert dropped == 0

    def test_empty(self) -> None:
        kept, dropped = rc.compact_current_turn_pins([], max_chars=100_000)
        assert kept == []
        assert dropped == 0


class TestPrepareRecentMessagesCompact:
    def test_off_parity_without_flag(self) -> None:
        """Without AGENT_LAB_COMMS_COMPACT, prepare_recent_messages is byte-stable."""
        msgs = _make_turn([
            ("claude", "first"),
            ("claude", "second"),
            ("cursor", "cursor reply"),
        ])
        os.environ.pop("AGENT_LAB_COMMS_COMPACT", None)
        trimmed, turns_om, chars_om, pin_count = rc.prepare_recent_messages(
            msgs, max_turns=2, max_chars=100_000
        )
        assert pin_count == 4  # human + 3 replies all pinned
        assert len(trimmed) == 4

    def test_compact_collapses_same_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENT_LAB_COMMS_COMPACT", "1")
        msgs = _make_turn([
            ("claude", "first claude reply"),
            ("claude", "latest claude reply"),
            ("cursor", "cursor reply"),
        ])
        trimmed, turns_om, chars_om, pin_count = rc.prepare_recent_messages(
            msgs, max_turns=2, max_chars=100_000, efficiency_mode=False
        )
        # Human + latest claude + cursor = 3 pins; one claude reply dropped.
        assert pin_count == 3
        assert sum(1 for m in trimmed if m.agent == "claude") == 1
        assert any(m.content == "latest claude reply" for m in trimmed)

    def test_efficiency_mode_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Efficiency mode keeps its own cap logic; compact branch is bypassed."""
        monkeypatch.setenv("AGENT_LAB_COMMS_COMPACT", "1")
        msgs = _make_turn([
            ("claude", "first"),
            ("claude", "second"),
            ("cursor", "cursor reply"),
        ])
        trimmed, turns_om, chars_om, pin_count = rc.prepare_recent_messages(
            msgs, max_turns=2, max_chars=100_000, efficiency_mode=True
        )
        # efficiency mode cap_pinned_messages path still runs
        assert pin_count >= 1


class TestBuildRecentTurnsBlockNote:
    def test_compact_dropped_note(self) -> None:
        msgs = [_Msg(role="user", content="hi", agent="human")]
        block, _ = rc.build_recent_turns_block(
            topic="t",
            messages=msgs,
            format_thread=lambda topic, msgs: "\n".join(m.content for m in msgs),
            turns_omitted=0,
            chars_omitted=0,
            compact_dropped=2,
        )
        assert "2 older same-agent reply(s) collapsed" in block
        assert "full text in chat.jsonl" in block

    def test_no_compact_no_note(self) -> None:
        msgs = [_Msg(role="user", content="hi", agent="human")]
        block, _ = rc.build_recent_turns_block(
            topic="t",
            messages=msgs,
            format_thread=lambda topic, msgs: "\n".join(m.content for m in msgs),
            turns_omitted=0,
            chars_omitted=0,
            compact_dropped=0,
        )
        assert "collapsed" not in block
