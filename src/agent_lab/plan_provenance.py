"""Plan decision provenance — extract (ref: chat.jsonl#Ln) from plan.md bullets."""

from __future__ import annotations

import re
from typing import Any

_REF_RE = re.compile(
    r"\(ref:\s*chat\.jsonl#L(\d+)(?:\s*[-–]\s*L?(\d+))?\)",
    re.I,
)
_SECTION_RE = re.compile(r"^##\s+(.+)$", re.M)


def extract_plan_provenance(plan_md: str) -> dict[str, list[dict[str, Any]]]:
    """Map plan section headings to ref entries found on bullets in that section."""
    if not (plan_md or "").strip():
        return {}
    sections: dict[str, list[dict[str, Any]]] = {}
    current = "_preamble"
    sections[current] = []
    for line in plan_md.splitlines():
        m = _SECTION_RE.match(line.strip())
        if m:
            current = m.group(1).strip()
            sections.setdefault(current, [])
            continue
        for ref_m in _REF_RE.finditer(line):
            start = int(ref_m.group(1))
            end = int(ref_m.group(2)) if ref_m.group(2) else start
            sections.setdefault(current, []).append(
                {
                    "line": start,
                    "line_end": end,
                    "raw": ref_m.group(0),
                    "snippet": line.strip()[:240],
                }
            )
    return {k: v for k, v in sections.items() if v}


def validate_plan_refs(
    plan_md: str,
    *,
    chat_line_count: int,
) -> list[dict[str, Any]]:
    """Return warnings for refs outside chat.jsonl line range."""
    issues: list[dict[str, Any]] = []
    if chat_line_count < 1:
        return issues
    for section, entries in extract_plan_provenance(plan_md).items():
        for ent in entries:
            ln = int(ent.get("line") or 0)
            end = int(ent.get("line_end") or ln)
            if ln < 1 or end > chat_line_count:
                issues.append(
                    {
                        "section": section,
                        "line": ln,
                        "line_end": end,
                        "reason": "out_of_range",
                        "chat_line_count": chat_line_count,
                    }
                )
    return issues
