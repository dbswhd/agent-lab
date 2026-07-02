"""Tests for context budget meta (Room token-opt session follow-ups)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_lab.context.meta import apply_invoke_follow_to_context_meta
from agent_lab.platform_md import read_platform_md_for_injection


@dataclass
class _Msg:
    role: str
    agent: str | None
    content: str
    visibility: str | None = None
    parallel_round: int | None = None


def test_combined_follow_included_in_layer_chars():
    meta = {
        "layer_chars": {"constraints": 100, "recent": 200, "total": 300},
        "turns_omitted": 0,
        "chars_omitted": 0,
    }
    apply_invoke_follow_to_context_meta(meta, "lead block\n\nhook block")
    assert meta["layer_chars"]["combined_follow"] == len("lead block\n\nhook block")
    assert meta["layer_chars"]["total"] == 300 + meta["layer_chars"]["combined_follow"]
    assert meta["budget_pct"] > 0


def test_combined_follow_empty_is_noop():
    meta = {"layer_chars": {"total": 100}, "turns_omitted": 0, "chars_omitted": 0}
    apply_invoke_follow_to_context_meta(meta, "   ")
    assert meta["layer_chars"]["total"] == 100
    assert "combined_follow" not in meta["layer_chars"]


def test_ten_turn_fixture_cap_reduces_ephemeral_count():
    from agent_lab.room.context.message_trim import cap_ephemeral_system_messages
    from agent_lab.room.team_orchestration import _SYNTHESIS_MARKER

    messages: list[_Msg] = [_Msg("user", None, f"turn {i}") for i in range(10)]
    for i in range(10):
        messages.append(
            _Msg(
                "system",
                None,
                f"{_SYNTHESIS_MARKER}\n\nsynth {i}",
                visibility="human",
            )
        )
    capped = cap_ephemeral_system_messages(messages, max_keep=3)
    synth_count = sum(1 for m in capped if _SYNTHESIS_MARKER in (m.content or ""))
    assert synth_count == 3
    assert len(capped) == 13  # 10 user + 3 synthesis


def test_cap_preserves_l_ref_object_identity():
    from agent_lab.room.context.message_trim import (
        cap_ephemeral_system_messages,
        format_thread_numbered_slice,
    )
    from agent_lab.room.team_orchestration import _SYNTHESIS_MARKER

    full: list[_Msg] = [_Msg("user", None, "hello")]
    for i in range(5):
        full.append(
            _Msg("system", None, f"{_SYNTHESIS_MARKER}\n\ns{i}", visibility="human")
        )
    capped = cap_ephemeral_system_messages(full, max_keep=2)
    text, start, end = format_thread_numbered_slice(full, capped)
    assert "L" in text
    assert start >= 1
    assert end >= start


def test_guidance_block_uses_mtime_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    agent_lab = tmp_path / ".agent-lab"
    agent_lab.mkdir()
    md = agent_lab / "PLATFORM.md"
    md.write_text("platform body", encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_ROOT", str(tmp_path))
    import agent_lab.platform_md as pm

    pm._read_cache.clear()
    reads = 0
    original_read = Path.read_text

    def counting_read(self: Path, *args, **kwargs):
        nonlocal reads
        if self.resolve() == md.resolve():
            reads += 1
        return original_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read)
    assert read_platform_md_for_injection()
    assert read_platform_md_for_injection()
    assert reads == 1


def test_compact_tool_output_runs_before_char_trim(monkeypatch: pytest.MonkeyPatch):
    from agent_lab.room.context.message_trim import prepare_recent_messages

    monkeypatch.delenv("AGENT_LAB_COMPACT_TOOL_OUTPUT", raising=False)
    fence = "```\n" + ("x" * 5000) + "\n```"
    messages = [
        _Msg("user", None, "q1"),
        _Msg("agent", "cursor", fence, parallel_round=1),
        _Msg("user", None, "q2"),
    ]
    trimmed, *_rest = prepare_recent_messages(messages, max_turns=8, max_chars=4000)
    agent_msg = next(m for m in trimmed if m.role == "agent")
    assert "truncated" in agent_msg.content or len(agent_msg.content) < len(fence) + 64
