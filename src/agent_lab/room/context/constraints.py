"""Constraints blocks, guidance constants, and gate/tag extraction."""

from __future__ import annotations

import re
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.context.limits import agent_context_limits
from agent_lab.room.context._shared import MessageLike

_STATUS_TAG_PREFIXES = ("[PROPOSED:", "[CONFIRMED-BY-HUMAN:")

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

FAST_TURN_GUIDANCE = """\
[Fast — solo agent · direct answer]
- **You are the only agent this turn.** Answer the Human directly; do not wait for peers or team consensus.
- Do **not** use `[PROPOSED:]` tables, ENDORSE/AMEND workflows, or "동료 의견을 기다립니다" / "제안에 대한 동료들의 의견".
- Do **not** ask the Human to approve a plan.md team workflow unless they explicitly requested a plan.
- Use workspace tools to verify repo claims, then give one **complete** reply (findings + recommendation).
- Human Inbox tools are off — if blocked, ask briefly in chat with concrete options, not orchestration theater.
- No envelope speech acts (ENDORSE/BLOCK/CHALLENGE) unless Human explicitly switched to Supervisor/consensus.
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
- Do **not** open with turn-mode meta ("discuss/plan 모드입니다", "이 턴은 discuss…") — policy is already in [고정 constraints]; answer substantively.
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

AGENT_CONNECT_HINT: dict[str, str] = {
    "cursor": (
        "이번 턴 각도: 레포·파일·구체적 다음 수정. "
        "경로·코드 질문이면 도구로 읽은 뒤 답할 것. "
        "동료의 범위·순서는 받아 이어가고, 같은 체크리스트만 반복하지 말 것."
    ),
    "codex": ("이번 턴 각도: 쪼개기·검증 순서·완료 기준. 동료의 사실·경로는 인용하고, 같은 분해만 다시 쓰지 말 것."),
    "claude": ("이번 턴 각도: 맹점·리스크·머지 전 확인. 동료는 이름으로 짚고, 새 근거·반론·질문만 추가."),
    "kimi_work": (
        "이번 턴 각도: Work peer — 레포 검증·대안 시각·약한 가정 도전. "
        "도구로 확인한 뒤 답할 것. 동료 ENDORSE/CHALLENGE를 인용하고 겹치는 체크리스트는 생략."
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

KIMI_WORK_TOOL_RULES = """\
[Kimi Work tools — this turn]
- Workspace-bound daimon tools first: read/search/verify before debating repo facts.
- Human Inbox (`ask_human` / `propose_build`) for direction blockers and GO — never ask forks in prose when inbox is on.
- Discuss 턴: 검증·제안만 — 패치/execute 주장 금지; 실행 제안은 `[PROPOSED: …]`.
- 턴 모드("discuss/plan")를 답변 첫 줄에 선언하지 말 것 — [고정 constraints]를 따름.
- Coordinate with Cursor/Codex/Claude per [Multi-agent coordination]; cite peer envelope acts when responding.
"""

KIMI_WORK_FAST_TOOL_RULES = """\
[Kimi Work · Fast solo turn]
- Read/search the workspace, then answer the Human in one complete reply.
- No `[PROPOSED:]`, ENDORSE/AMEND, plan.md team tables, or waiting for peer reactions.
- No Human Inbox tools — state direction questions in plain chat if truly blocked.
- Do not claim execute/patch completion; verification and recommendations only unless Human asked to implement.
"""

REPLY_FORMAT_RULES = CONVERSATION_GUIDANCE


def agent_tool_rules(
    agent: str,
    run_meta: RunStateLike | None = None,
    *,
    active_agents: list[str] | None = None,
) -> str:
    from agent_lab.room.preset import is_fast_room_session
    from agent_lab.room.roster_context import active_agents_from_run_meta, peer_coordination_hint

    active = active_agents if active_agents is not None else active_agents_from_run_meta(run_meta)
    peer_hint = peer_coordination_hint(active, agent)
    peer_line = f"\n- In-room peers this turn: {peer_hint}."
    if agent == "kimi_work" and is_fast_room_session(run_meta):
        return KIMI_WORK_FAST_TOOL_RULES
    if agent == "claude":
        return CLAUDE_TOOL_RULES + peer_line
    if agent == "cursor":
        return CURSOR_TOOL_RULES.replace(
            "coordinate with Codex/Claude per [Multi-agent coordination]",
            f"coordinate with in-room peers ({peer_hint}) per [Multi-agent coordination]",
        )
    if agent == "codex":
        return CODEX_TOOL_RULES.replace(
            "Coordinate with Cursor/Claude: see [Multi-agent coordination]",
            f"Coordinate with in-room peers ({peer_hint}): see [Multi-agent coordination]",
        )
    if agent == "kimi_work":
        return KIMI_WORK_TOOL_RULES.replace(
            "Coordinate with Cursor/Codex/Claude per [Multi-agent coordination]",
            f"Coordinate with in-room peers ({peer_hint}) per [Multi-agent coordination]",
        )
    return ""


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


def extract_human_gates(messages: list[MessageLike], topic: str = "") -> list[str]:
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
    messages: list[MessageLike],
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


def build_constraints_block(
    *,
    permission_lines: str,
    human_gates: list[str],
    agreed_bullets: list[str],
    status_tags: list[str] | None = None,
    workspace_lines: str = "",
    active_agents: list[str] | None = None,
    team_lead: str | None = None,
) -> str:
    parts: list[str] = ["[고정 constraints]"]
    if workspace_lines.strip():
        parts.append(workspace_lines.strip())
    if active_agents:
        from agent_lab.room.roster_context import build_active_roster_block

        roster = build_active_roster_block(active_agents, team_lead=team_lead)
        if roster.strip():
            parts.append(roster.strip())
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
