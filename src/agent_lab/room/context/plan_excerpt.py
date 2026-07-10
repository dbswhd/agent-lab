"""Plan.md excerpt parsing for agent context."""

from __future__ import annotations

import re

from agent_lab.run.state import RunStateLike

from agent_lab.consensus_agreements import (
    agreement_sync_failed_notice,
    pending_consensus_agreements,
)
from agent_lab.core.limits import agent_context_limits

_AGREED_HEADERS = (
    "합의된 점",
    "합의 (채택",
    "합의된 점 (채택",
    "tl;dr",
    "tldr",
)
_OPEN_HEADERS = (
    "쟁점 / 미결정",
    "쟁점/미결정",
    "미결정",
    "보류 리스크",
    "must-not",
    "must not",
)


def split_plan_sections(plan_md: str) -> dict[str, str]:
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


def section_body(sections: dict[str, str], header_prefixes: tuple[str, ...]) -> str:
    for key, body in sections.items():
        for prefix in header_prefixes:
            if key.startswith(prefix.lower()) or prefix.lower() in key:
                return body
    return ""


def bullet_lines(body: str, *, max_items: int, max_chars: int) -> list[str]:
    lines: list[str] = []
    total = 0
    for raw in body.splitlines():
        line = raw.strip()
        if not line.startswith("-") and not line.startswith("*"):
            continue
        item = line.lstrip("-* ").strip()
        if not item or item.startswith("("):
            continue
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
    sections = split_plan_sections(plan_md)
    body = section_body(sections, _AGREED_HEADERS)
    return bullet_lines(
        body,
        max_items=agent_context_limits().max_agreed_items,
        max_chars=5000,
    )


def extract_open_bullets(plan_md: str) -> list[str]:
    sections = split_plan_sections(plan_md)
    body = section_body(sections, _OPEN_HEADERS)
    return bullet_lines(body, max_items=agent_context_limits().max_open_items, max_chars=7000)


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


def plan_stale_banner(run_meta: RunStateLike | None) -> str | None:
    """Prompt plan sync when a consensus topic is agreed but not yet in plan.md."""
    if not run_meta:
        return None
    pending = pending_consensus_agreements(run_meta.get("consensus_agreements"))
    if not pending:
        return None
    excerpt = str(pending[-1].get("excerpt") or "")
    return agreement_sync_failed_notice(excerpt, "plan.md 자동 정리 후 수동 확인 필요")
