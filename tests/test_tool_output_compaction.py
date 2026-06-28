"""P2 tool-output auto-compaction (AGENT_LAB_COMPACT_TOOL_OUTPUT, default off).

Covers AC1-AC10 of the ralplan plan: deterministic head+tail+marker truncation of
over-cap code-fence blocks in pre-current-turn agent messages, copy-on-truncate
(never in-place), pins/user untouched, OFF-parity, malformed-fence determinism.
"""

from __future__ import annotations

from dataclasses import dataclass, field


from agent_lab.room import context as rc


@dataclass
class _Msg:
    role: str
    agent: str | None
    content: str
    parallel_round: int | None = None
    extra: dict = field(default_factory=dict)


def _fence(inner: str) -> str:
    return f"```\n{inner}\n```"


# ---------------------------------------------------------------------------
# helper-level: _truncate_fenced_blocks
# ---------------------------------------------------------------------------


def test_ac1_over_cap_block_truncated_head_tail_marker():
    cap = 100
    inner = "X" * 500
    content = _fence(inner)
    out = rc._truncate_fenced_blocks(content, cap)
    assert "[...truncated " in out
    assert out != content
    # head/tail are cap//2 each of the INNER (the inner here is "\n" + X*500 + "\n")
    block_inner = "\n" + inner + "\n"
    removed = len(block_inner) - 2 * (cap // 2)
    assert f"[...truncated {removed} chars...]" in out


def test_ac2_under_cap_block_intact():
    cap = 2000
    content = _fence("small output")
    assert rc._truncate_fenced_blocks(content, cap) == content


def test_ac7_determinism_and_exact_split():
    cap = 100
    inner = "abcdefgh" * 100  # 800 chars
    content = _fence(inner)
    out1 = rc._truncate_fenced_blocks(content, cap)
    out2 = rc._truncate_fenced_blocks(content, cap)
    assert out1 == out2
    block_inner = "\n" + inner + "\n"
    head = cap // 2
    tail = cap // 2
    removed = len(block_inner) - head - tail
    expected = (
        "```"
        + block_inner[:head]
        + f"[...truncated {removed} chars...]"
        + block_inner[len(block_inner) - tail :]
        + "```"
    )
    assert out1 == expected


def test_ac6_non_fence_prose_untouched():
    cap = 10
    content = "just a long line of prose with no code fence " * 20
    assert rc._truncate_fenced_blocks(content, cap) == content


def test_ac10_malformed_unterminated_fence_deterministic():
    cap = 50
    inner = "Y" * 400
    content = "prose before\n```\n" + inner  # unterminated fence runs to EOC
    out1 = rc._truncate_fenced_blocks(content, cap)
    out2 = rc._truncate_fenced_blocks(content, cap)
    assert out1 == out2
    assert "[...truncated " in out1
    assert out1.startswith("prose before\n")


def test_ac10_exact_cap_boundary_not_truncated():
    cap = 100
    inner = "Z" * cap  # inner length == cap → NOT truncated (strictly greater only)
    out = rc._truncate_fenced_blocks(f"```{inner}```", cap)
    assert out == f"```{inner}```"


def test_multiple_blocks_independent():
    cap = 40
    big = "A" * 200
    small = "ok"
    content = _fence(big) + "\nmiddle prose\n" + _fence(small)
    out = rc._truncate_fenced_blocks(content, cap)
    assert "[...truncated " in out
    assert "middle prose" in out
    assert "ok" in out  # small block survives


# ---------------------------------------------------------------------------
# message-level: _truncate_old_tool_outputs (copy-on-truncate, identity)
# ---------------------------------------------------------------------------


def test_ac3_pins_never_truncated():
    cap = 50
    big = _fence("Q" * 400)
    user = _Msg(role="user", agent=None, content="do the thing")
    old_agent = _Msg(role="agent", agent="codex", content=big)
    pinned_agent = _Msg(role="agent", agent="claude", content=big)
    recent = [user, old_agent, pinned_agent]
    pinned = [user, pinned_agent]  # current turn pins
    out = rc._truncate_old_tool_outputs(recent, pinned, cap=cap)
    # old non-pinned agent truncated (copy)
    assert out[1].content != old_agent.content
    assert "[...truncated " in out[1].content
    # pinned agent passed through at SAME identity, content intact
    assert out[2] is pinned_agent
    assert out[2].content == big


def test_ac10_originals_unmodified_and_copy_identity():
    cap = 50
    big = _fence("W" * 400)
    old_agent = _Msg(role="agent", agent="codex", content=big)
    recent = [old_agent]
    out = rc._truncate_old_tool_outputs(recent, [], cap=cap)
    # original object byte-unchanged
    assert old_agent.content == big
    # returned object is a DIFFERENT object (copy)
    assert out[0] is not old_agent
    assert out[0].content != big
    # other fields preserved by dataclasses.replace
    assert out[0].role == "agent"
    assert out[0].agent == "codex"


def test_ac6_user_and_human_messages_untouched():
    cap = 50
    big_user = _Msg(role="user", agent=None, content=_fence("U" * 400))
    recent = [big_user]
    out = rc._truncate_old_tool_outputs(recent, [], cap=cap)
    assert out[0] is big_user  # non-agent passthrough at same identity


def test_non_dataclass_passthrough():
    cap = 50

    class _DuckMsg:
        role = "agent"
        agent = "x"
        content = _fence("D" * 400)

    m = _DuckMsg()
    recent = [m]
    out = rc._truncate_old_tool_outputs(recent, [], cap=cap)
    # not a dataclass → passthrough unchanged (no partial copy)
    assert out[0] is m


def test_agent_message_without_fence_untouched():
    cap = 50
    m = _Msg(role="agent", agent="codex", content="plain reply no fence " * 50)
    out = rc._truncate_old_tool_outputs([m], [], cap=cap)
    assert out[0] is m


# ---------------------------------------------------------------------------
# integration: prepare_recent_messages seam + OFF-parity
# ---------------------------------------------------------------------------


def _make_thread() -> list[_Msg]:
    big = _fence("L" * 6000)
    return [
        _Msg(role="user", agent=None, content="turn1 question"),
        _Msg(role="agent", agent="codex", content=big),
        _Msg(role="agent", agent="claude", content=big),
        _Msg(role="user", agent=None, content="turn2 follow up"),
        _Msg(role="agent", agent="cursor", content=_fence("R" * 6000)),
    ]


def test_ac5_off_parity_byte_identical(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_COMPACT_TOOL_OUTPUT", raising=False)
    monkeypatch.delenv("AGENT_LAB_COMMS_COMPACT", raising=False)
    thread = _make_thread()
    off1 = rc.prepare_recent_messages(thread, max_chars=5000, compact=False)
    monkeypatch.setenv("AGENT_LAB_COMPACT_TOOL_OUTPUT", "0")
    off2 = rc.prepare_recent_messages(thread, max_chars=5000, compact=False)
    assert [m.content for m in off1[0]] == [m.content for m in off2[0]]
    assert off1[1:] == off2[1:]


def test_ac1_ac4_on_reduces_old_tool_output(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_COMPACT_TOOL_OUTPUT", "1")
    monkeypatch.setenv("AGENT_LAB_COMPACT_TOOL_CHARS", "200")
    monkeypatch.delenv("AGENT_LAB_COMMS_COMPACT", raising=False)
    thread = _make_thread()
    on = rc.prepare_recent_messages(thread, max_chars=5000, compact=False)
    joined = "".join(m.content for m in on[0])
    # at least one old tool block was truncated
    assert "[...truncated " in joined


def test_ac4_turn_count_preserved(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_COMPACT_TOOL_OUTPUT", "1")
    monkeypatch.setenv("AGENT_LAB_COMPACT_TOOL_CHARS", "200")
    monkeypatch.delenv("AGENT_LAB_COMMS_COMPACT", raising=False)
    thread = _make_thread()
    # max_chars high enough that compaction resolves overflow → no turn drop
    on = rc.prepare_recent_messages(thread, max_chars=20000, compact=False)
    # both user turns still present
    user_contents = [m.content for m in on[0] if m.role == "user"]
    assert "turn1 question" in user_contents
    assert "turn2 follow up" in user_contents


def test_cap_helper_defaults_and_validation(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_COMPACT_TOOL_CHARS", raising=False)
    assert rc._tool_output_char_cap() == 2000
    monkeypatch.setenv("AGENT_LAB_COMPACT_TOOL_CHARS", "not-a-number")
    assert rc._tool_output_char_cap() == 2000
    monkeypatch.setenv("AGENT_LAB_COMPACT_TOOL_CHARS", "-5")
    assert rc._tool_output_char_cap() == 2000
    monkeypatch.setenv("AGENT_LAB_COMPACT_TOOL_CHARS", "512")
    assert rc._tool_output_char_cap() == 512


def test_enabled_helper(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_COMPACT_TOOL_OUTPUT", raising=False)
    assert rc._compact_tool_output_enabled() is False
    monkeypatch.setenv("AGENT_LAB_COMPACT_TOOL_OUTPUT", "1")
    assert rc._compact_tool_output_enabled() is True
