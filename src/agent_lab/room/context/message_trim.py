"""Message trimming, thread formatting, and scribe context assembly."""

from __future__ import annotations

import dataclasses
import os
from typing import Any

from agent_lab.context.limits import agent_context_limits, scribe_context_limits
from agent_lab.room._typing import agent_label
from agent_lab.room.context._shared import MessageLike, env_bool, message_chars


def count_messages(messages: list[MessageLike]) -> int:
    return len(messages)


def current_turn_message_count(messages: list[MessageLike]) -> int:
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return len(messages)
    return len(messages) - last_user


def _split_human_turns(messages: list[MessageLike]) -> list[list[MessageLike]]:
    turns: list[list[MessageLike]] = []
    current: list[MessageLike] = []
    for m in messages:
        if m.role == "user" and current:
            turns.append(current)
            current = []
        current.append(m)
    if current:
        turns.append(current)
    return turns


def recent_messages_by_turns(
    messages: list[MessageLike],
    *,
    max_turns: int | None = None,
) -> tuple[list[MessageLike], int]:
    """Keep messages from the last N human turns (each turn = user + agent replies)."""
    if max_turns is None:
        max_turns = agent_context_limits().recent_turns
    if not messages or max_turns <= 0:
        return messages, 0
    turns = _split_human_turns(messages)
    if len(turns) <= max_turns:
        return messages, 0
    kept = turns[-max_turns:]
    flat: list[MessageLike] = [m for t in kept for m in t]
    return flat, len(turns) - len(kept)


def trim_messages_by_chars(
    messages: list[MessageLike],
    *,
    max_chars: int | None = None,
) -> tuple[list[MessageLike], int]:
    if max_chars is None:
        max_chars = agent_context_limits().max_thread_chars
    if not messages:
        return messages, 0
    total = 0
    kept: list[MessageLike] = []
    for m in reversed(messages):
        chunk = len(m.content) + 64
        if total + chunk > max_chars and kept:
            break
        kept.insert(0, m)
        total += chunk
    omitted = len(messages) - len(kept)
    return kept, omitted


def compact_current_turn_pins(
    messages: list[MessageLike],
    *,
    max_chars: int,
) -> tuple[list[MessageLike], int]:
    """Keep latest Human + latest reply per agent; cap by dropping oldest agent replies."""
    if not messages:
        return list(messages), 0
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return list(messages), 0
    human = messages[last_user]
    agents = messages[last_user + 1 :]
    seen: set[str] = set()
    latest_per_agent: list[MessageLike] = []
    for m in reversed(agents):
        key = getattr(m, "agent", None) or m.role
        if key not in seen:
            seen.add(key)
            latest_per_agent.append(m)
    latest_per_agent.reverse()
    orig_count = len(agents) + 1
    kept: list[MessageLike] = [human] + latest_per_agent
    dropped = orig_count - len(kept)
    while len(kept) > 1 and message_chars(kept) > max_chars:
        kept.pop(-1)
        dropped += 1
    return kept, dropped


def cap_pinned_messages(
    pinned: list[MessageLike],
    *,
    max_messages: int,
    max_chars: int,
) -> tuple[list[MessageLike], int]:
    """Shrink current-turn pins: keep Human + newest agent replies within caps."""
    if not pinned:
        return pinned, 0
    orig_len = len(pinned)
    last_user = -1
    for i, m in enumerate(pinned):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        agents = list(pinned)
        human: MessageLike | None = None
    else:
        human = pinned[last_user]
        agents = pinned[last_user + 1 :]
    max_agents = max(1, max_messages - (1 if human else 0))
    agents = agents[-max_agents:]
    kept: list[MessageLike] = ([human] if human else []) + agents

    def _pin_chars(msgs: list[MessageLike]) -> int:
        return sum(len(m.content) + 64 for m in msgs)

    while _pin_chars(kept) > max_chars and len(agents) > 1:
        agents.pop(0)
        kept = ([human] if human else []) + agents
    return kept, orig_len - len(kept)


def pinned_current_turn_messages(messages: list[MessageLike]) -> list[MessageLike]:
    """Last Human message and every reply in the same turn — never dropped by char trim."""
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return list(messages)
    return messages[last_user:]


def trim_messages_by_chars_pinned(
    messages: list[MessageLike],
    *,
    max_chars: int | None = None,
    pinned: list[MessageLike] | None = None,
) -> tuple[list[MessageLike], int]:
    """Char trim from the oldest side; `pinned` messages are always kept in order."""
    if max_chars is None:
        max_chars = agent_context_limits().max_thread_chars
    if not messages:
        return messages, 0
    pin = pinned if pinned is not None else pinned_current_turn_messages(messages)
    pin_ids = {id(m) for m in pin}
    rest = [m for m in messages if id(m) not in pin_ids]
    pin_chars = sum(len(m.content) + 64 for m in pin)
    budget = max(max_chars - pin_chars, 4096)
    trimmed_rest, omitted = trim_messages_by_chars(rest, max_chars=budget)
    rest_kept_ids = {id(m) for m in trimmed_rest}
    merged: list[MessageLike] = [m for m in messages if id(m) in pin_ids or id(m) in rest_kept_ids]
    return merged, omitted


def _compact_tool_output_enabled() -> bool:
    return env_bool("AGENT_LAB_COMPACT_TOOL_OUTPUT")


def _tool_output_char_cap() -> int:
    raw = os.getenv("AGENT_LAB_COMPACT_TOOL_CHARS")
    if raw is None:
        return 2000
    try:
        val = int(raw.strip())
    except (TypeError, ValueError):
        return 2000
    return val if val > 0 else 2000


def _truncate_fenced_blocks(content: str, cap: int) -> str:
    if cap <= 0 or "```" not in content:
        return content
    parts = content.split("```")
    head = cap // 2
    tail = cap // 2
    changed = False
    for i in range(1, len(parts), 2):
        inner = parts[i]
        if len(inner) > cap:
            removed = len(inner) - head - tail
            parts[i] = inner[:head] + f"[...truncated {removed} chars...]" + inner[len(inner) - tail :]
            changed = True
    if not changed:
        return content
    return "```".join(parts)


def _truncate_old_tool_outputs(
    recent: list[MessageLike],
    pinned: list[MessageLike],
    *,
    cap: int,
) -> list[MessageLike]:
    if cap <= 0:
        return recent
    pin_ids = {id(m) for m in pinned}
    out: list[MessageLike] = []
    for m in recent:
        if id(m) in pin_ids or getattr(m, "role", None) != "agent":
            out.append(m)
            continue
        content = getattr(m, "content", None)
        if not isinstance(content, str) or "```" not in content:
            out.append(m)
            continue
        new_content = _truncate_fenced_blocks(content, cap)
        if new_content == content or not dataclasses.is_dataclass(m):
            out.append(m)
            continue
        out.append(dataclasses.replace(m, content=new_content))
    return out


def _ephemeral_system_max_keep() -> int:
    raw = os.getenv("AGENT_LAB_EPHEMERAL_SYSTEM_MAX_KEEP")
    if raw is None:
        return 3
    try:
        val = int(raw.strip())
    except (TypeError, ValueError):
        return 3
    return max(0, val)


def _is_ephemeral_peer_digest(m: MessageLike) -> bool:
    if m.role != "system":
        return False
    return "peer digest" in (m.content or "").lower()


def _is_ephemeral_synthesis(m: MessageLike) -> bool:
    if m.role != "system":
        return False
    from agent_lab.room.team_orchestration import is_human_synthesis_message

    visibility = getattr(m, "visibility", None)
    return is_human_synthesis_message(m.content or "", visibility)


def cap_ephemeral_system_messages(
    messages: list[MessageLike],
    *,
    max_keep: int | None = None,
) -> list[MessageLike]:
    """Keep only the newest N peer-digest and synthesis system messages."""
    if max_keep is None:
        max_keep = _ephemeral_system_max_keep()
    if max_keep <= 0 or not messages:
        return list(messages)

    drop: set[int] = set()
    for predicate in (_is_ephemeral_peer_digest, _is_ephemeral_synthesis):
        indices = [i for i, m in enumerate(messages) if predicate(m)]
        if len(indices) > max_keep:
            drop.update(indices[: len(indices) - max_keep])
    if not drop:
        return list(messages)
    return [m for i, m in enumerate(messages) if i not in drop]


def prepare_recent_messages(
    messages: list[MessageLike],
    *,
    max_turns: int | None = None,
    max_chars: int | None = None,
    efficiency_mode: bool = False,
    compact: bool | None = None,
) -> tuple[list[MessageLike], int, int, int]:
    """Turn cap → ephemeral system cap → char trim with current Human turn pinned."""
    from agent_lab.context.limits import efficiency_limits

    if compact is None:
        compact = env_bool("AGENT_LAB_COMMS_COMPACT")
    lim = agent_context_limits()
    eff = efficiency_limits() if efficiency_mode else None
    max_turns = max_turns if max_turns is not None else (eff.recent_turns if eff else lim.recent_turns)
    max_chars = max_chars if max_chars is not None else lim.max_thread_chars
    recent, turns_omitted = recent_messages_by_turns(messages, max_turns=max_turns)
    recent = cap_ephemeral_system_messages(recent)
    pinned = pinned_current_turn_messages(recent)
    compact_dropped = 0
    if compact and not efficiency_mode:
        pin_budget = max(4096, int(max_chars * 0.25))
        pinned, compact_dropped = compact_current_turn_pins(recent, max_chars=pin_budget)
        current_all = pinned_current_turn_messages(recent)
        kept_ids = {id(m) for m in pinned}
        dropped_ids = {id(m) for m in current_all if id(m) not in kept_ids}
        if dropped_ids:
            recent = [m for m in recent if id(m) not in dropped_ids]
    elif eff:
        pin_budget = max(4096, int(max_chars * eff.pin_budget_pct / 100))
        pinned, _ = cap_pinned_messages(
            pinned,
            max_messages=eff.max_pin_messages,
            max_chars=pin_budget,
        )
    if _compact_tool_output_enabled() and message_chars(recent) > max_chars:
        recent = _truncate_old_tool_outputs(recent, pinned, cap=_tool_output_char_cap())
    trimmed, chars_omitted = trim_messages_by_chars_pinned(recent, max_chars=max_chars, pinned=pinned)
    return trimmed, turns_omitted, chars_omitted, len(pinned)


def format_thread_numbered_slice(
    all_messages: list[MessageLike],
    slice_messages: list[MessageLike],
) -> tuple[str, int, int]:
    """Numbered thread preserving chat.jsonl L indices for a message slice."""
    if not slice_messages:
        return "", 0, 0
    line_numbers: list[int] = []
    for m in slice_messages:
        try:
            line_numbers.append(all_messages.index(m) + 1)
        except ValueError:
            line_numbers.append(0)
    if line_numbers and line_numbers[0] > 0:
        start = line_numbers[0] - 1
    else:
        start = max(0, len(all_messages) - len(slice_messages))
        line_numbers = [start + offset + 1 for offset in range(len(slice_messages))]
    lines: list[str] = []
    for line_no, m in zip(line_numbers, slice_messages, strict=True):
        if m.role == "user":
            lines.append(f"L{line_no} Human:\n{m.content}\n")
        elif m.role == "agent" and m.agent:
            lines.append(f"L{line_no} {agent_label(m.agent)}:\n{m.content}\n")
        else:
            lines.append(f"L{line_no} System:\n{m.content}\n")
    first_l = line_numbers[0] if line_numbers else 0
    last_l = line_numbers[-1] if line_numbers else 0
    return "\n".join(lines), first_l, last_l


def format_agent_numbered_thread(
    topic: str,
    slice_messages: list[MessageLike],
    all_messages: list[MessageLike],
) -> str:
    numbered, first_l, last_l = format_thread_numbered_slice(all_messages, slice_messages)
    header = f"Human topic:\n{topic.strip()}\n"
    if first_l and last_l:
        header += f"\n[chat.jsonl line refs: L{first_l}..L{last_l} in this block; cite as chat.jsonl#Ln]\n"
    return f"{header}\n{numbered}".strip()


def agent_thread_formatter(
    all_messages: list[MessageLike],
    *,
    numbered: bool,
) -> Any:
    """Return format_thread(topic, slice) using plain or L-numbered lines."""

    def _format(topic: str, slice_messages: list[MessageLike]) -> str:
        if numbered:
            return format_agent_numbered_thread(topic, slice_messages, all_messages)
        lines = [f"Human topic:\n{topic.strip()}\n"]
        for m in slice_messages:
            if m.role == "user":
                lines.append(f"Human:\n{m.content}\n")
            elif m.role == "agent" and m.agent:
                lines.append(f"{agent_label(m.agent)}:\n{m.content}\n")
        return "\n".join(lines)

    return _format


def scribe_thread_block(
    all_messages: list[MessageLike],
    *,
    max_turns: int | None = None,
    max_chars: int | None = None,
) -> str:
    """Trim scribe input while keeping valid L{{n}} refs for the included slice."""
    sl = scribe_context_limits()
    if sl.full_thread:
        numbered, _, _ = format_thread_numbered_slice(all_messages, all_messages)
        return numbered

    turns_cap = max_turns if max_turns is not None else sl.recent_turns
    chars_cap = max_chars if max_chars is not None else sl.max_chars
    recent, turns_omitted = recent_messages_by_turns(all_messages, max_turns=turns_cap)
    trimmed, chars_omitted = trim_messages_by_chars(recent, max_chars=chars_cap)
    numbered, first_l, last_l = format_thread_numbered_slice(all_messages, trimmed)
    notes: list[str] = []
    if turns_omitted:
        notes.append(f"{turns_omitted} earlier human turn(s) omitted from this scribe input")
    if chars_omitted:
        notes.append(f"{chars_omitted} older message(s) trimmed by size")
    if notes:
        numbered = (
            f"[Scribe context: L{first_l}..L{last_l} only. "
            + "; ".join(notes)
            + ". Use only these L numbers in refs; else (ref: 불명확).]\n\n"
            + numbered
        )
    return numbered


def build_recent_turns_block(
    *,
    topic: str,
    messages: list[MessageLike],
    format_thread: Any,
    all_messages: list[MessageLike] | None = None,
    turns_omitted: int,
    chars_omitted: int,
    peer_deduped: int = 0,
    compact_dropped: int = 0,
    numbered: bool = False,
) -> tuple[str, str]:
    lim = agent_context_limits()
    line_range = ""
    if numbered and all_messages and messages:
        _, first_l, last_l = format_thread_numbered_slice(all_messages, messages)
        if first_l and last_l:
            line_range = f"L{first_l}–L{last_l}"
    header = f"[최근 N턴] (last {lim.recent_turns} human turns"
    if turns_omitted:
        header += f"; {turns_omitted} earlier turn(s) omitted"
    if chars_omitted:
        header += f"; {chars_omitted} older message(s) trimmed by size"
    if peer_deduped:
        header += f"; {peer_deduped} peer line(s) only in [이번 턴 · 동료 발화]"
    if compact_dropped:
        header += f"; {compact_dropped} older same-agent reply(s) collapsed"
    header += " — full log in chat.jsonl)"
    thread = format_thread(topic, messages)
    note_parts: list[str] = []
    if turns_omitted or chars_omitted:
        note_parts.append("earlier context omitted from this payload — use constraints + plan 미결")
    if peer_deduped:
        note_parts.append("peer replies in this turn appear only in [이번 턴 · 동료 발화]")
    if compact_dropped:
        note_parts.append(f"{compact_dropped} older same-agent reply collapsed; full text in chat.jsonl")
    note = ""
    if note_parts:
        note = "\n[Note: " + "; ".join(note_parts) + ".]\n\n"
    return f"{header}\n{note}{thread}".strip(), line_range
