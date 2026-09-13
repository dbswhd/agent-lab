"""Quality boundary for idea-lane candidate replies.

The idea lane receives provider prose, but downstream selection and planning need
small, explicit guarantees.  This module keeps the original reply for audit while
returning a human-facing body with internal narration removed and repository claims
classified until they have evidence.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

IDEATION_OUTPUT_CONTRACT = "ideation.v1"
IDEATION_REQUIRED_FIELDS = (
    "title",
    "principle",
    "usage",
    "difference",
    "tradeoff",
    "first_experiment",
)

# These are provider-process sentences observed in live pilots.  Keep the list
# deliberately narrow so legitimate product prose mentioning a repository stays.
_META_LINE_PATTERNS = (
    re.compile(r"^(?:agent lab|에이전트 랩)\s*(?:의|에서|강의|레포|프로토콜)", re.I),
    re.compile(r"^(?:이제|먼저)\s*(?:레포|파일|코드|폴더|문서).*(?:확인|살펴|읽어|검토)", re.I),
    re.compile(r"^(?:레포|파일|코드|폴더|문서).*(?:확인하|살펴보|읽어보|검토하)", re.I),
    re.compile(r"^(?:도구|툴).*(?:호출|사용|확인하)", re.I),
    re.compile(r"^(?:사용자에게|휴먼에게).*(?:질문하|물어보)", re.I),
)

_REPO_CLAIM_PATTERNS = (
    re.compile(r"(?:레포|리포지토리|코드베이스|코드|파일|폴더).*(?:있다|존재|구축|구현|확인)", re.I),
    re.compile(r"(?:이미|현재).*(?:구현|완료|동작|구축).*(?:있다|한다)", re.I),
    re.compile(r"(?:^|\s)(?:src|app|tests|docs|scripts)/[\w./_-]+"),
    re.compile(r"(?:^|\s)/Users/[\w./~ _-]+"),
)

_EVIDENCE_MARKERS = ("ref:", "근거:", "출처:", "확인 경로:", "#l", "line ")


def sanitize_ideation_text(text: str) -> tuple[str, list[str]]:
    """Remove internal process narration while preserving substantive prose.

    Returns ``(cleaned_text, removed_lines)``.  The caller can retain the original
    text separately for audit and debugging.
    """
    body = str(text or "").strip()
    if not body:
        return "", []
    kept: list[str] = []
    removed: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if line and any(pattern.search(line) for pattern in _META_LINE_PATTERNS):
            removed.append(line)
            continue
        kept.append(raw.rstrip())
    cleaned = "\n".join(kept).strip()
    return cleaned, removed


def unverified_repo_claims(text: str) -> list[str]:
    """Return repository claims that lack an inline evidence marker.

    A claim is not deleted.  Downstream synthesis must treat returned lines as
    assumptions requiring review rather than as repository facts.
    """
    claims: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or any(marker in line.lower() for marker in _EVIDENCE_MARKERS):
            continue
        if any(pattern.search(line) for pattern in _REPO_CLAIM_PATTERNS):
            claims.append(line[:240])
    return claims


def contract_quality(
    fields: Mapping[str, Any],
    *,
    meta_removed: list[str] | None = None,
    repo_claims: list[str] | None = None,
) -> dict[str, Any]:
    """Describe whether a parsed candidate is safe for final synthesis."""
    missing = [name for name in IDEATION_REQUIRED_FIELDS if not str(fields.get(name) or "").strip()]
    blocked_claims = list(repo_claims or [])
    status = "ready" if not missing and not blocked_claims else "needs_review"
    return {
        "contract": IDEATION_OUTPUT_CONTRACT,
        "status": status,
        "missing_fields": missing,
        "meta_lines_removed": len(meta_removed or []),
        "unverified_repo_claims": blocked_claims,
    }


def option_is_synthesis_ready(option: Mapping[str, Any]) -> bool:
    """Only fully shaped, evidence-safe options may feed final plan synthesis."""
    quality = option.get("quality")
    if isinstance(quality, Mapping):
        return str(quality.get("status") or "") == "ready"
    return all(str(option.get(name) or "").strip() for name in IDEATION_REQUIRED_FIELDS)


def ideation_synthesis_block(run_meta: Mapping[str, Any] | None) -> str:
    """Render selected idea state as a constrained input for the final Scribe pass."""
    if not isinstance(run_meta, Mapping):
        return ""
    state = run_meta.get("ideation")
    if not isinstance(state, Mapping):
        return ""
    options = [option for option in state.get("options") or [] if isinstance(option, Mapping)]
    selection = state.get("selection") if isinstance(state.get("selection"), Mapping) else None
    selected_id = str((selection or {}).get("option_id") or "")
    selected = next((option for option in options if str(option.get("id") or "") == selected_id), None)
    ready = [option for option in options if option_is_synthesis_ready(option)]
    lines = [
        "Idea-lane synthesis contract:",
        f"contract: {IDEATION_OUTPUT_CONTRACT}",
        "Use only the selected option and synthesis-ready fields below as design facts.",
        "Treat every assumption, missing field, or unverified repository claim as unresolved; do not promote it to fact.",
        f"selected_option_id: {selected_id or '(none)'}",
        f"synthesis_ready_option_ids: {', '.join(str(o.get('id')) for o in ready) or '(none)'}",
    ]
    if selected:
        lines.append("selected_option:")
        for name in IDEATION_REQUIRED_FIELDS:
            value = str(selected.get(name) or "").strip()
            if value:
                lines.append(f"- {name}: {value}")
        quality = selected.get("quality")
        if isinstance(quality, Mapping) and quality.get("unverified_repo_claims"):
            lines.append(f"- review_required_repo_claims: {quality.get('unverified_repo_claims')}")
    return "\n".join(lines)
