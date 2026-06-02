"""Scribe enrichment for objections and agent contributions (E2 / H1)."""

from __future__ import annotations

import re
from typing import Any

from agent_lab.agent_envelope import envelope_act, parse_agent_response
from agent_lab.room_objections import list_objections, open_objections

_PROPOSED_RE = re.compile(r"\[PROPOSED:\s*([^\]]+)\]", re.I)
_REF_LINE_RE = re.compile(r"chat\.jsonl#L(\d+)", re.I)
_SUMMARY_ACTS = frozenset({"BLOCK", "CHALLENGE", "ENDORSE", "PASS", "AMEND", "PROPOSE"})
_MAX_AGENT_SUMMARY_CHARS = 400


def format_unresolved_objections_section(run_meta: dict[str, Any] | None) -> str:
    rows = open_objections(run_meta)
    if not rows:
        return ""
    lines = ["## 미해결 이의", ""]
    for o in rows[:12]:
        ref = o.get("target_ref") or o.get("task_id") or "—"
        lines.append(
            f"- **{o.get('from')}** · {o.get('act')} → {ref}: {(o.get('body') or '')[:200]}"
        )
    lines.append("")
    lines.append(
        "(Human이 작업 바에서 수용/기각하기 전까지 linked plan execute는 차단됩니다.)"
    )
    return "\n".join(lines)


def blocked_plan_action_indices(run_meta: dict[str, Any] | None) -> list[int]:
    out: list[int] = []
    for o in open_objections(run_meta):
        if o.get("act") != "BLOCK":
            continue
        idx = o.get("plan_action_index")
        if idx is not None:
            try:
                out.append(int(idx))
            except (TypeError, ValueError):
                pass
    return sorted(set(out))


def _latest_human_turn_bounds(messages: list[Any]) -> tuple[int, int]:
    """Return (last_user_index, end_exclusive) for the latest human turn slice."""
    last_user = -1
    for i, m in enumerate(messages):
        if getattr(m, "role", None) == "user":
            last_user = i
    if last_user < 0:
        return -1, len(messages)
    return last_user, len(messages)


def _message_line_no(messages: list[Any], index: int) -> int:
    return index + 1


def _first_body_line(body: str) -> str:
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        return line[:200]
    return ""


def _claim_bullets(body: str, *, max_items: int = 4) -> list[str]:
    bullets: list[str] = []
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line.startswith(("-", "*")):
            continue
        item = line.lstrip("-* ").strip()
        if not item or item.startswith("("):
            continue
        item = _REF_LINE_RE.sub("", item).strip()
        if len(item) < 4:
            continue
        bullets.append(item[:120])
        if len(bullets) >= max_items:
            break
    return bullets


def _proposed_lines(body: str) -> list[str]:
    return [m.group(1).strip()[:100] for m in _PROPOSED_RE.finditer(body or "")][:3]


def _first_chat_ref(body: str, envelope: dict[str, Any] | None) -> str | None:
    for ref in (envelope or {}).get("refs") or []:
        text = str(ref).strip()
        if text:
            return text[:80]
    m = _REF_LINE_RE.search(body or "")
    if m:
        return f"chat.jsonl#L{m.group(1)}"
    return None


def extract_agent_turn_summaries(
    messages: list[Any],
    run_meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Per-agent diff summaries for the latest human turn (H1 — not verbatim)."""
    del run_meta  # reserved for future run_meta hints
    last_user, end = _latest_human_turn_bounds(messages)
    if last_user < 0 and not messages:
        return []
    turn_start = last_user + 1 if last_user >= 0 else 0
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for i in range(turn_start, end):
        m = messages[i]
        if getattr(m, "role", None) != "agent":
            continue
        agent = str(getattr(m, "agent", "") or "").strip().lower()
        if not agent or agent in seen:
            continue
        seen.add(agent)
        raw = getattr(m, "content", "") or ""
        parsed = parse_agent_response(raw)
        body = (parsed.body or raw).strip()
        env = getattr(m, "envelope", None) or (
            parsed.envelope.to_dict() if parsed.envelope else None
        )
        act = envelope_act(env)
        line_no = _message_line_no(messages, i)
        bullets = _claim_bullets(body)
        if not bullets:
            headline = _first_body_line(body)
            if headline:
                bullets = [headline[:160]]
        proposed = _proposed_lines(body)
        first_ref = _first_chat_ref(body, env)
        summary: dict[str, Any] = {
            "agent": agent,
            "line_no": line_no,
            "bullets": bullets,
            "proposed": proposed,
            "first_ref": first_ref,
        }
        if act and act in _SUMMARY_ACTS:
            summary["act"] = act
            refs = list((env or {}).get("refs") or [])[:4]
            if refs:
                summary["act_refs"] = refs
        parts: list[str] = []
        if act and act in _SUMMARY_ACTS:
            ref_tail = f" → {', '.join(summary.get('act_refs') or [])}" if summary.get(
                "act_refs"
            ) else ""
            parts.append(f"**{act}**{ref_tail}")
        for b in bullets:
            parts.append(f"• {b}")
        for p in proposed:
            parts.append(f"• [PROPOSED:] {p}")
        if first_ref and f"L{line_no}" not in first_ref:
            parts.append(f"• ref: {first_ref}")
        text = "\n".join(parts)
        if len(text) > _MAX_AGENT_SUMMARY_CHARS:
            text = text[: _MAX_AGENT_SUMMARY_CHARS - 1].rstrip() + "…"
        summary["text"] = text
        out.append(summary)
    return out


def format_scribe_agent_summaries_block(
    messages: list[Any],
    run_meta: dict[str, Any] | None = None,
) -> str:
    """Structured agent-input block for scribe (replaces full verbatim thread)."""
    summaries = extract_agent_turn_summaries(messages, run_meta)
    if not summaries:
        return ""
    lines = [
        "Agent summaries (latest human turn — cite chat.jsonl#Ln where shown):",
        "",
    ]
    for row in summaries:
        agent = str(row.get("agent") or "").strip()
        line_no = row.get("line_no")
        label = agent.capitalize() if agent else "Agent"
        header = f"### {label}"
        if line_no:
            header += f" (L{line_no} → chat.jsonl#L{line_no})"
        lines.append(header)
        lines.append(str(row.get("text") or "").strip())
        lines.append("")
    lines.append(
        "(Full verbatim agent replies omitted — synthesize from summaries + enrichment below.)"
    )
    return "\n".join(lines).strip()


def build_agent_contributions_section(messages: list[Any]) -> str:
    """Multi-bullet per-agent diff for plan ## 에이전트별 기여 (자동)."""
    summaries = extract_agent_turn_summaries(messages)
    if not summaries:
        return ""
    lines = ["## 에이전트별 기여 (자동)", ""]
    for row in summaries:
        agent = str(row.get("agent") or "").strip()
        if not agent:
            continue
        label = agent.capitalize()
        line_no = row.get("line_no")
        prefix = f"- **{label}**"
        if line_no:
            prefix += f" (L{line_no})"
        lines.append(prefix + ":")
        act = row.get("act")
        if act:
            refs = row.get("act_refs") or []
            ref_s = f" → {', '.join(refs)}" if refs else ""
            lines.append(f"  - {act}{ref_s}")
        for b in row.get("bullets") or []:
            lines.append(f"  - {b}")
        for p in row.get("proposed") or []:
            lines.append(f"  - [PROPOSED:] {p}")
    if len(lines) <= 2:
        return ""
    return "\n".join(lines)


def agent_contributions_section(messages: list[Any]) -> str:
    """Alias for plan enrichment (H1)."""
    return build_agent_contributions_section(messages)


def build_scribe_enrichment(
    run_meta: dict[str, Any] | None,
    messages: list[Any],
) -> str:
    parts: list[str] = []
    parts.append(
        "[Scribe · isolation hint]\n"
        "For each executable 3-field action, keep `where` paths under one git root. "
        "If paths span repos, mark it gated or add `- isolation: block`; "
        "for non-git file work, add `- isolation: apply`."
    )
    blocked = blocked_plan_action_indices(run_meta)
    if blocked:
        nums = ", ".join(str(n) for n in blocked)
        parts.append(
            f"[Scribe · execute hold]\n"
            f"Open BLOCK covers plan action index(es): {nums}. "
            f"Do NOT list these under ## 지금 실행 as executable 3-field actions. "
            f"Include them under ## 미해결 이의 or ## 실행 순서 (이후) as blocked/gated only."
        )
    obj_sec = format_unresolved_objections_section(run_meta)
    if obj_sec:
        parts.append(
            "[Scribe · objections]\n"
            "Include the following section verbatim (update if already present):\n\n"
            + obj_sec
        )
    contrib = agent_contributions_section(messages)
    if contrib:
        parts.append(
            "[Scribe · contributions]\n"
            "Include or merge this auto summary under plan (do not drop agent names):\n\n"
            + contrib
        )
    resolved = [
        o
        for o in list_objections(run_meta)
        if o.get("status") in ("resolved_accepted", "resolved_wontfix")
    ][-6:]
    if resolved:
        lines = ["[Scribe · resolved objections — for audit]", ""]
        for o in resolved:
            lines.append(
                f"- {o.get('id')}: {o.get('status')} — {(o.get('body') or '')[:80]}"
            )
        parts.append("\n".join(lines))
    return "\n\n---\n\n".join(parts)


def should_skip_scribe_for_open_objections(
    run_meta: dict[str, Any] | None,
    *,
    mode: str,
    synthesize: bool,
) -> bool:
    """E2b: pure discuss turn with open objections — skip scribe (no plan churn)."""
    if not synthesize:
        return False
    if mode == "plan":
        return False
    return bool(open_objections(run_meta))


def patch_plan_objections_only(
    plan_md: str,
    run_meta: dict[str, Any] | None,
) -> str:
    """Append or replace ## 미해결 이의 when scribe skipped (E2b)."""
    section = format_unresolved_objections_section(run_meta)
    if not section.strip():
        return plan_md
    body = (plan_md or "").strip()
    header = "## 미해결 이의"
    if header in body:
        before, _, _after = body.partition(header)
        return before.rstrip() + "\n\n" + section.strip() + "\n"
    if body:
        return body + "\n\n" + section.strip() + "\n"
    return section.strip() + "\n"
