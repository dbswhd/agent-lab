"""Trimmed room context for agent CLI calls (not scribe)."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Protocol

from agent_lab.context_limits import agent_context_limits, scribe_context_limits
from agent_lab.consensus_agreements import (
    agreement_sync_failed_notice,
    pending_consensus_agreements,
)

# Backward-compatible module-level defaults (prefer agent_context_limits() at runtime).
RECENT_TURNS = agent_context_limits().recent_turns
MAX_THREAD_CHARS = agent_context_limits().max_thread_chars

_STATUS_TAG_PREFIXES = ("[PROPOSED:", "[CONFIRMED-BY-HUMAN:")

_AGREED_HEADERS = (
    "합의된 점",
    "합의 (채택",
    "합의된 점 (채택",
)
_OPEN_HEADERS = (
    "쟁점 / 미결정",
    "쟁점/미결정",
    "미결정",
    "보류 리스크",
)

_GATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"수정.*(말|하지)\s*말", re.I), "no-edits"),
    (re.compile(r"함부로.*(수정|하지)", re.I), "no-casual-edits"),
    (re.compile(r"구현.*(말|하지)\s*말|말고.*논의", re.I), "discuss-only"),
    (re.compile(r"논의만|토론만|의견만", re.I), "discuss-only"),
    (re.compile(r"코드.*(변경|수정).*(금지|하지)", re.I), "no-code"),
    (re.compile(r"don't\s+(implement|edit|change)", re.I), "no-edits"),
    (re.compile(r"discussion\s+only|no\s+(code|implementation)", re.I), "discuss-only"),
    (re.compile(r"trim\s*구현\s*OK", re.I), "trim-ok"),
    (re.compile(r"채택|보류|미결", re.I), "decision"),
    (re.compile(r"스펙으로만|선행조건", re.I), "spec-only"),
    (re.compile(r"scribe.*(생략|안)|정리.*(안|말고)", re.I), "no-scribe"),
]

ANALYSIS_TURN_GUIDANCE = """\
[분석 턴 — 현황 파악만]
- **관찰·사실·파일/로그 근거**만 보고하세요. plan.md는 건드리지 않습니다.
- `[PROPOSED:]` / 구현·수정 제안 / 반박 / 「이의 없습니다」는 **이 턴에서 쓰지 마세요**.
- 동료와 겹치면 짧게 — 같은 파일을 반복 탐색하지 말고, 각자 다른 각도(구조·리스크·데이터)를 보세요.
- 모르면 「확인 필요: …」 한 줄로 남기세요.
"""

EFFICIENCY_RESPONSE_GUIDANCE = """\
[효율 모드 — 구독 호출·payload 절약]
- 답변은 **800자 이내**를 목표로 하세요(Human이 길게 요청한 경우만 예외).
- 불릿 3개 이하, 동료와 겹치는 문장은 생략.
- 합의 확인 시 이의 없으면 첫 줄만 `이의 없습니다`.
"""

CONVERSATION_GUIDANCE = """\
[Conversation guidance — debate evolves through action + feedback, not monologue]
- This room is **not text-only**: read the repo, run checks, sketch fixes when that advances the thread.
- React to peers with **evidence** (what you read/ran/changed) and build on their findings — mutual feedback, not three parallel essays.
- Write for a Human reader: clear stance, concrete reasoning, and what you did or would do next.
- Peer lines are already in your context ([이번 턴 · 동료 발화] / peer digest) — **do not** echo that header; name peers only when citing something new.
- Prefer short paragraphs after tool work; do not repeat the whole thread or re-introduce yourself.
- If you truly add nothing new, say so briefly (e.g. PASS or "앞선 의견과 동일").
- In **자유 토론** consensus rounds: if you have **no** objection and **nothing new** to add, use `act: ENDORSE` in the envelope (body: `이의 없습니다` one line) or legacy first-line `이의 없습니다` only.
- If you agree **but** want to add risks, steps, or new work items, use `act: AMEND` / `PROPOSE` — do **not** lead with `이의 없습니다`.
- New risks or open questions belong in plan 미결, not buried in debate filler.
- `[PROPOSED: …]` — only when proposing **new actionable work** for the shared task board (not every reply).
- `[CONFIRMED-BY-HUMAN: …]` — only after explicit Human approval; never promote `[PROPOSED:]` yourself.
"""

MULTI_AGENT_COORDINATION = """\
[Multi-agent coordination — Cursor · Codex · Claude, one workspace]
- You **may** read/run/edit in this turn when it helps the debate move forward (Human granted full access).
- **Avoid collisions:** before editing a file a peer likely touched this turn, **Read** it first.
- **R1 (parallel):** prefer disjoint paths (analysis vs test vs patch in different files). If the same file is hot, **one editor per wave** — others review, verify, or `[PROPOSED:]` without overwriting.
- **R2+ (sequential):** you see peer outputs — **extend or fix**, do not blindly revert; state what you changed and why.
- Never silent-merge conflicting edits; flag conflict in `[PROPOSED:]` and let peers AMEND/ENDORSE — not a Human questionnaire.
- Codex/Cursor/Claude: complementary roles still apply, but **all may use tools** when useful.
"""

PEER_DECISION_GUIDANCE = """\
[Peer decision — settle resolvable choices together]
- Resolve scope, approach, file choice, and verify order among Cursor/Codex/Claude — state a **working assumption**, tag `[PROPOSED: …]`, and let peers ENDORSE / AMEND in the next round.
- Escalate to Human for: explicit approval gates (`GO`, budget, destructive prod), missing secrets/paths outside repo, a genuine fork, or unresolvable peer conflict after one amend round.
- Prefer **deciding together** on resolvable details over a low-value "Human에게 한 줄 확인".
"""

# One-line complementarity hint per agent (connect without format forcing).
AGENT_CONNECT_HINT: dict[str, str] = {
    "cursor": (
        "이번 턴 각도: 레포·파일·구체적 다음 수정. "
        "경로·코드 질문이면 도구로 읽은 뒤 답할 것. "
        "동료의 범위·순서는 받아 이어가고, 같은 체크리스트만 반복하지 말 것."
    ),
    "codex": (
        "이번 턴 각도: 쪼개기·검증 순서·완료 기준. "
        "동료의 사실·경로는 인용하고, 같은 분해만 다시 쓰지 말 것."
    ),
    "claude": (
        "이번 턴 각도: 맹점·리스크·머지 전 확인. "
        "동료는 이름으로 짚고, 새 근거·반론·질문만 추가."
    ),
}

CLAUDE_TOOL_RULES = """\
[Claude Code tools]
- If the human asks to read, verify, quote, or check a file/path: call **Read** or **Grep** first, then answer from the result.
- Runtime and --add-dir roots are in [고정 constraints]; do not claim claude.ai-only or missing filesystem access.
"""

CURSOR_TOOL_RULES = """\
[Cursor SDK tools — this turn]
- File/code/UI/build questions: **read or search the repo in `cwd` first**, then answer or edit. Do not guess from chat context alone.
- After edits: **re-read or run the verification** the human or plan asked for when you can in this turn.
- Workspace roots are in [고정 constraints]; coordinate with Codex/Claude per [Multi-agent coordination].
"""

CODEX_TOOL_RULES = """\
[Codex CLI tools — this turn]
- You may read/search/run shell in granted project roots — use them to **verify** peer claims and advance the debate.
- **Cap exploration:** 1–3 short reads/greps, then **answer in this turn**. Do not chain many ls/find/cat loops.
- Prefer execution order + test runs; after Codex edits, say what you ran and what passed/failed.
- Coordinate with Cursor/Claude: see [Multi-agent coordination]; do not overwrite a peer's edit without reading first.
"""


def agent_tool_rules(agent: str) -> str:
    if agent == "claude":
        return CLAUDE_TOOL_RULES
    if agent == "cursor":
        return CURSOR_TOOL_RULES
    if agent == "codex":
        return CODEX_TOOL_RULES
    return ""

# Backward-compatible alias for imports/tests.
REPLY_FORMAT_RULES = CONVERSATION_GUIDANCE


def is_pass_response(text: str) -> bool:
    """True when first line is exactly PASS (used for UI/events; scribe keeps full log)."""
    if not text.strip():
        return False
    first_line = text.lstrip().splitlines()[0].strip()
    return first_line.upper() == "PASS"


def is_pure_no_objection(text: str) -> bool:
    """True only when the reply is consent-only (no amendment tail)."""
    if not text.strip():
        return False
    lines = [ln.strip() for ln in text.lstrip().splitlines() if ln.strip()]
    if not lines or lines[0] != "이의 없습니다":
        return False
    if len(lines) == 1:
        return True
    if len(lines) == 2:
        second = lines[1]
        if second.startswith("(") and second.endswith(")") and len(second) <= 80:
            return True
    return False


def is_no_objection_response(text: str) -> bool:
    """True when reply is pure 「이의 없습니다」 (free-discuss consensus end)."""
    return is_pure_no_objection(text)


class _MessageLike(Protocol):
    role: str
    agent: str | None
    content: str
    parallel_round: int | None


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _split_plan_sections(plan_md: str) -> dict[str, str]:
    """Map lowercased header key → body text."""
    if not plan_md.strip():
        return {}
    sections: dict[str, str] = {}
    current_key = ""
    buf: list[str] = []
    for line in plan_md.splitlines():
        if line.startswith("## "):
            if current_key:
                sections[current_key] = "\n".join(buf).strip()
            header = line[3:].strip()
            current_key = header.lower()
            buf = []
        elif current_key:
            buf.append(line)
    if current_key:
        sections[current_key] = "\n".join(buf).strip()
    return sections


def _section_body(sections: dict[str, str], header_prefixes: tuple[str, ...]) -> str:
    for key, body in sections.items():
        for prefix in header_prefixes:
            if key.startswith(prefix.lower()) or prefix.lower() in key:
                return body
    return ""


def count_messages(messages: list[_MessageLike]) -> int:
    return len(messages)


def current_turn_message_count(messages: list[_MessageLike]) -> int:
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return len(messages)
    return len(messages) - last_user


def agent_thread_formatter(
    all_messages: list[_MessageLike],
    *,
    numbered: bool,
) -> Any:
    """Return format_thread(topic, slice) using plain or L-numbered lines."""

    def _format(topic: str, slice_messages: list[_MessageLike]) -> str:
        if numbered:
            return format_agent_numbered_thread(topic, slice_messages, all_messages)
        from agent_lab.agents.registry import label

        lines = [f"Human topic:\n{topic.strip()}\n"]
        for m in slice_messages:
            if m.role == "user":
                lines.append(f"Human:\n{m.content}\n")
            elif m.role == "agent" and m.agent:
                lines.append(f"{label(m.agent)}:\n{m.content}\n")
        return "\n".join(lines)

    return _format


def format_agent_numbered_thread(
    topic: str,
    slice_messages: list[_MessageLike],
    all_messages: list[_MessageLike],
) -> str:
    numbered, first_l, last_l = format_thread_numbered_slice(all_messages, slice_messages)
    header = f"Human topic:\n{topic.strip()}\n"
    if first_l and last_l:
        header += (
            f"\n[chat.jsonl line refs: L{first_l}..L{last_l} in this block; "
            "cite as chat.jsonl#Ln]\n"
        )
    return f"{header}\n{numbered}".strip()


def _bullet_lines(body: str, *, max_items: int, max_chars: int) -> list[str]:
    lines: list[str] = []
    total = 0
    for raw in body.splitlines():
        line = raw.strip()
        if not line.startswith("-") and not line.startswith("*"):
            continue
        item = line.lstrip("-* ").strip()
        if not item or item.startswith("("):
            continue
        # Drop ref tails for constraints brevity
        item = re.sub(r"\s*\(ref:.*\)\s*$", "", item, flags=re.I).strip()
        if len(item) < 4:
            continue
        if len(lines) >= max_items:
            break
        if total + len(item) > max_chars and lines:
            break
        lines.append(item)
        total += len(item)
    return lines


def extract_agreed_bullets(plan_md: str) -> list[str]:
    sections = _split_plan_sections(plan_md)
    body = _section_body(sections, _AGREED_HEADERS)
    return _bullet_lines(
        body,
        max_items=agent_context_limits().max_agreed_items,
        max_chars=5000,
    )


def extract_open_bullets(plan_md: str) -> list[str]:
    sections = _split_plan_sections(plan_md)
    body = _section_body(sections, _OPEN_HEADERS)
    return _bullet_lines(
        body, max_items=agent_context_limits().max_open_items, max_chars=7000
    )


def extract_human_gates(messages: list[_MessageLike], topic: str = "") -> list[str]:
    seen: set[str] = set()
    gates: list[str] = []

    def add(snippet: str) -> None:
        s = snippet.strip()
        if len(s) < 4 or s in seen:
            return
        seen.add(s)
        gates.append(s[:240])

    if topic.strip():
        for pat, _ in _GATE_PATTERNS:
            if pat.search(topic):
                add(topic.strip()[:240])
                break

    for m in messages:
        if m.role != "user":
            continue
        for line in m.content.splitlines():
            line = line.strip()
            if not line:
                continue
            for pat, _ in _GATE_PATTERNS:
                if pat.search(line):
                    add(line)
                    break
        if len(gates) >= agent_context_limits().max_gate_lines:
            break
    return gates[: agent_context_limits().max_gate_lines]


def extract_status_tags(
    messages: list[_MessageLike],
    *,
    max_items: int | None = None,
) -> list[str]:
    """Collect [PROPOSED:] / [CONFIRMED-BY-HUMAN:] lines from recent discuss messages."""
    cap = max_items if max_items is not None else agent_context_limits().max_status_tags
    seen: set[str] = set()
    tags: list[str] = []
    for m in messages:
        for line in m.content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            upper = stripped.upper()
            if not any(upper.startswith(p) for p in _STATUS_TAG_PREFIXES):
                continue
            key = stripped.lower()
            if key in seen:
                continue
            seen.add(key)
            tags.append(stripped)
            if len(tags) >= cap:
                return tags
    return tags


def plan_stale_banner(run_meta: dict[str, Any] | None) -> str | None:
    """Prompt plan sync when a consensus topic is agreed but not yet in plan.md."""
    if not run_meta:
        return None
    pending = pending_consensus_agreements(run_meta.get("consensus_agreements"))
    if not pending:
        return None
    excerpt = str(pending[-1].get("excerpt") or "")
    return agreement_sync_failed_notice(excerpt, "plan.md 자동 정리 후 수동 확인 필요")


def _split_human_turns(messages: list[_MessageLike]) -> list[list[_MessageLike]]:
    turns: list[list[_MessageLike]] = []
    current: list[_MessageLike] = []
    for m in messages:
        if m.role == "user" and current:
            turns.append(current)
            current = []
        current.append(m)
    if current:
        turns.append(current)
    return turns


def recent_messages_by_turns(
    messages: list[_MessageLike],
    *,
    max_turns: int = RECENT_TURNS,
) -> tuple[list[_MessageLike], int]:
    """Keep messages from the last N human turns (each turn = user + agent replies)."""
    if not messages or max_turns <= 0:
        return messages, 0
    turns = _split_human_turns(messages)
    if len(turns) <= max_turns:
        return messages, 0
    kept = turns[-max_turns:]
    flat: list[_MessageLike] = [m for t in kept for m in t]
    return flat, len(turns) - len(kept)


def trim_messages_by_chars(
    messages: list[_MessageLike],
    *,
    max_chars: int = MAX_THREAD_CHARS,
) -> tuple[list[_MessageLike], int]:
    if not messages:
        return messages, 0
    total = 0
    kept: list[_MessageLike] = []
    for m in reversed(messages):
        chunk = len(m.content) + 64
        if total + chunk > max_chars and kept:
            break
        kept.insert(0, m)
        total += chunk
    omitted = len(messages) - len(kept)
    return kept, omitted


def cap_pinned_messages(
    pinned: list[_MessageLike],
    *,
    max_messages: int,
    max_chars: int,
) -> tuple[list[_MessageLike], int]:
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
        human: _MessageLike | None = None
    else:
        human = pinned[last_user]
        agents = pinned[last_user + 1 :]
    max_agents = max(1, max_messages - (1 if human else 0))
    agents = agents[-max_agents:]
    kept: list[_MessageLike] = ([human] if human else []) + agents

    def _pin_chars(msgs: list[_MessageLike]) -> int:
        return sum(len(m.content) + 64 for m in msgs)

    while _pin_chars(kept) > max_chars and len(agents) > 1:
        agents.pop(0)
        kept = ([human] if human else []) + agents
    return kept, orig_len - len(kept)


def pinned_current_turn_messages(messages: list[_MessageLike]) -> list[_MessageLike]:
    """Last Human message and every reply in the same turn — never dropped by char trim."""
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return list(messages)
    return messages[last_user:]


def trim_messages_by_chars_pinned(
    messages: list[_MessageLike],
    *,
    max_chars: int = MAX_THREAD_CHARS,
    pinned: list[_MessageLike] | None = None,
) -> tuple[list[_MessageLike], int]:
    """Char trim from the oldest side; `pinned` messages are always kept in order."""
    if not messages:
        return messages, 0
    pin = pinned if pinned is not None else pinned_current_turn_messages(messages)
    pin_ids = {id(m) for m in pin}
    rest = [m for m in messages if id(m) not in pin_ids]
    pin_chars = sum(len(m.content) + 64 for m in pin)
    budget = max(max_chars - pin_chars, 4096)
    trimmed_rest, omitted = trim_messages_by_chars(rest, max_chars=budget)
    rest_kept_ids = {id(m) for m in trimmed_rest}
    merged: list[_MessageLike] = [
        m for m in messages if id(m) in pin_ids or id(m) in rest_kept_ids
    ]
    return merged, omitted


def prepare_recent_messages(
    messages: list[_MessageLike],
    *,
    max_turns: int | None = None,
    max_chars: int | None = None,
    efficiency_mode: bool = False,
) -> tuple[list[_MessageLike], int, int, int]:
    """Turn cap → char trim with current Human turn pinned. Returns (msgs, turns_om, chars_om, pin_count)."""
    from agent_lab.context_limits import efficiency_limits

    lim = agent_context_limits()
    eff = efficiency_limits() if efficiency_mode else None
    max_turns = max_turns if max_turns is not None else (eff.recent_turns if eff else lim.recent_turns)
    max_chars = max_chars if max_chars is not None else lim.max_thread_chars
    recent, turns_omitted = recent_messages_by_turns(messages, max_turns=max_turns)
    pinned = pinned_current_turn_messages(recent)
    if eff:
        pin_budget = max(4096, int(max_chars * eff.pin_budget_pct / 100))
        pinned, _ = cap_pinned_messages(
            pinned,
            max_messages=eff.max_pin_messages,
            max_chars=pin_budget,
        )
    trimmed, chars_omitted = trim_messages_by_chars_pinned(
        recent, max_chars=max_chars, pinned=pinned
    )
    return trimmed, turns_omitted, chars_omitted, len(pinned)


def collect_peer_messages(
    messages: list[_MessageLike],
    agent: str,
    parallel_round: int,
) -> list[_MessageLike]:
    """Messages shown in [이번 턴 · 동료 발화] for this agent and round."""
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    turn_msgs = messages[last_user + 1 :] if last_user >= 0 else messages
    same_round = [
        m
        for m in turn_msgs
        if m.role == "agent"
        and m.agent
        and m.agent != agent
        and (m.parallel_round or 1) == parallel_round
    ]
    if same_round:
        return same_round
    if parallel_round > 1:
        prev = parallel_round - 1
        return [
            m
            for m in turn_msgs
            if m.role == "agent"
            and m.agent
            and m.agent != agent
            and (m.parallel_round or 1) == prev
        ]
    return []


def dedupe_peer_from_recent(
    recent: list[_MessageLike],
    peer_msgs: list[_MessageLike],
) -> tuple[list[_MessageLike], int]:
    """Drop agent lines from [최근 N턴] that already appear in [동료 발화]."""
    if not peer_msgs:
        return recent, 0
    peer_ids = {id(m) for m in peer_msgs}
    out: list[_MessageLike] = []
    removed = 0
    for m in recent:
        if m.role == "agent" and id(m) in peer_ids:
            removed += 1
            continue
        out.append(m)
    return out, removed


def format_peer_block(peer_msgs: list[_MessageLike]) -> str:
    if not peer_msgs:
        return ""
    from agent_lab.agents.registry import label

    lines = ["[이번 턴 · 동료 발화]"]
    for m in peer_msgs:
        body = (m.content or "").strip()
        if body and m.agent:
            lines.append(f"{label(m.agent)}:\n{body}\n")
    return "\n".join(lines).strip()


def build_constraints_block(
    *,
    permission_lines: str,
    human_gates: list[str],
    agreed_bullets: list[str],
    status_tags: list[str] | None = None,
    workspace_lines: str = "",
) -> str:
    parts: list[str] = ["[고정 constraints]"]
    if workspace_lines.strip():
        parts.append(workspace_lines.strip())
    if permission_lines.strip():
        parts.append(permission_lines.strip())
    if human_gates:
        parts.append("Human gates (from topic / user messages):")
        parts.extend(f"- {g}" for g in human_gates)
    if status_tags:
        parts.append("Status tags (from recent discuss):")
        parts.extend(f"- {t}" for t in status_tags)
    if agreed_bullets:
        parts.append("합의된 점 (from plan.md, excerpt):")
        parts.extend(f"- {b}" for b in agreed_bullets)
    if len(parts) == 1:
        parts.append("(none — follow room role and Human topic.)")
    return "\n".join(parts)


def build_plan_open_block(
    *,
    open_bullets: list[str],
    stale_line: str | None,
) -> str:
    parts: list[str] = ["[plan 미결]"]
    if stale_line:
        parts.append(stale_line)
    if open_bullets:
        parts.extend(f"- {b}" for b in open_bullets)
    else:
        parts.append("(no open items section in plan.md)")
    return "\n".join(parts)


def format_thread_numbered_slice(
    all_messages: list[_MessageLike],
    slice_messages: list[_MessageLike],
) -> tuple[str, int, int]:
    """Numbered thread preserving chat.jsonl L indices for a message slice."""
    if not slice_messages:
        return "", 0, 0
    try:
        start = all_messages.index(slice_messages[0])
    except ValueError:
        start = max(0, len(all_messages) - len(slice_messages))
    lines: list[str] = []
    for offset, m in enumerate(slice_messages):
        line_no = start + offset + 1
        if m.role == "user":
            lines.append(f"L{line_no} Human:\n{m.content}\n")
        elif m.role == "agent" and m.agent:
            from agent_lab.agents.registry import label

            lines.append(f"L{line_no} {label(m.agent)}:\n{m.content}\n")
        else:
            lines.append(f"L{line_no} System:\n{m.content}\n")
    first_l = start + 1
    last_l = start + len(slice_messages)
    return "\n".join(lines), first_l, last_l


def scribe_thread_block(
    all_messages: list[_MessageLike],
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


def collect_r1_turn_replies(messages: list[_MessageLike]) -> list[_MessageLike]:
    """Agent round-1 replies in the current human turn (for R1.5 bridge)."""
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return []
    out: list[_MessageLike] = []
    for m in messages[last_user + 1 :]:
        if m.role == "agent" and (m.parallel_round or 1) == 1:
            out.append(m)
    return out


def _r15_bridge_enabled() -> bool:
    return os.getenv("AGENT_LAB_R15", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def build_turn_bridge_block(
    messages: list[_MessageLike],
    *,
    parallel_round: int,
    max_chars: int = 400,
) -> str:
    """Optional R1 summary before round 2+ (AGENT_LAB_R15=1)."""
    if parallel_round < 2 or not _r15_bridge_enabled():
        return ""
    from agent_lab.agents.registry import label

    r1 = collect_r1_turn_replies(messages)
    if not r1:
        return ""
    lines: list[str] = []
    for m in r1:
        if not m.agent:
            continue
        first = (m.content or "").strip().split("\n", 1)[0][:120]
        if first:
            lines.append(f"- {label(m.agent)}: {first}")
    if not lines:
        return ""
    body = "\n".join(lines)
    if len(body) > max_chars:
        body = body[: max_chars - 1].rsplit("\n", 1)[0] + "…"
    return f"[R1 요약 · bridge]\n{body}"


def build_peer_round_block(
    messages: list[_MessageLike],
    agent: str,
    parallel_round: int,
) -> str:
    """Format [이번 턴 · 동료 발화] for one agent round (backward-compatible API)."""
    return format_peer_block(collect_peer_messages(messages, agent, parallel_round))


def build_recent_turns_block(
    *,
    topic: str,
    messages: list[_MessageLike],
    format_thread: Any,
    all_messages: list[_MessageLike] | None = None,
    turns_omitted: int,
    chars_omitted: int,
    peer_deduped: int = 0,
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
        header += (
            f"; {peer_deduped} peer line(s) only in [이번 턴 · 동료 발화]"
        )
    header += " — full log in chat.jsonl)"
    thread = format_thread(topic, messages)
    note_parts: list[str] = []
    if turns_omitted or chars_omitted:
        note_parts.append(
            "earlier context omitted from this payload — use constraints + plan 미결"
        )
    if peer_deduped:
        note_parts.append(
            "peer replies in this turn appear only in [이번 턴 · 동료 발화]"
        )
    note = ""
    if note_parts:
        note = "\n[Note: " + "; ".join(note_parts) + ".]\n\n"
    return f"{header}\n{note}{thread}".strip(), line_range
