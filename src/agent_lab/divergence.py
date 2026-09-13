"""발산(divergence) turn-profile helpers.

Divergence is an additive discussion-phase mode: agents hold distinct
positions without premature consensus and the room returns a bounded list of
approach-distinct alternative options, then stops. No selection, no execute
linkage — the human chooses from the options list.
"""

from __future__ import annotations

from typing import Any

# Accept both the Korean label used in the UI and the ascii id.
DIVERGENCE_PROFILES = frozenset({"divergence", "발산"})

# Cap the options list so the seat returns a small, comparable set.
# (Lower bound is guidance for the agents, not enforced here — it depends on
# how many seats actually reply.)
MAX_DIVERGENCE_OPTIONS = 4


def is_divergence_profile(turn_profile: str | None) -> bool:
    """True when the turn profile selects divergence mode."""
    return (turn_profile or "").strip().lower() in DIVERGENCE_PROFILES


def _reply_field(reply: Any, *names: str) -> str:
    """Read the first non-empty attribute/key among ``names`` (duck-typed)."""
    for name in names:
        if isinstance(reply, dict):
            value = reply.get(name)
        else:
            value = getattr(reply, name, None)
        if value:
            return str(value)
    return ""


def format_divergence_options(replies: list[Any]) -> list[dict[str, str]]:
    """Format agent replies into a bounded list of approach-distinct options.

    One option per agent reply, capped at ``MAX_DIVERGENCE_OPTIONS``. The list
    is the terminal artifact of a divergence run: callers present it for human
    selection and MUST NOT auto-advance to execute. Distinctness of approaches
    is the human's judgement call, not enforced here.
    """
    options: list[dict[str, str]] = []
    for reply in replies:
        from agent_lab.room.context.ideation_quality import sanitize_ideation_text

        approach, _removed = sanitize_ideation_text(_reply_field(reply, "content", "text", "message"))
        approach = approach.strip()
        if not approach:
            continue
        options.append(
            {
                "index": str(len(options) + 1),
                "agent": _reply_field(reply, "agent", "role", "name"),
                "approach": approach,
            }
        )
        if len(options) >= MAX_DIVERGENCE_OPTIONS:
            break
    return options


# --- structured idea options (RI-06) ---------------------------------------
#
# The idea lane needs candidates the user can actually compare: what it is, how
# it works, where it would be used, how it differs, what it gives up, and the
# smallest first experiment. Parsing is tolerant and never destructive — a
# reply that does not follow the shape is kept verbatim with a parse_error so
# the user still sees what the model said (§RI-06).

import re

_LABEL_PATTERNS: dict[str, tuple[str, ...]] = {
    "title": ("제목", "title", "이름"),
    "principle": ("핵심 작동 원리", "작동 원리", "핵심 원리", "원리", "작동 방식", "principle", "how it works"),
    "usage": ("실제 사용 장면", "사용 장면", "사용 예", "사용 시나리오", "usage", "scenario"),
    "difference": ("다른 접근과 무엇이 다른지", "다른 점", "차이", "차별점", "difference"),
    "tradeoff": ("tradeoff", "트레이드오프", "포기하는 것", "대가"),
    "first_experiment": (
        "이 구상에서 가장 먼저 확인할 작은 실험",
        "가장 먼저 확인할 작은 실험",
        "첫 실험",
        "가장 작은 실험",
        "실험",
        "first experiment",
    ),
}

# `- **제목:** 이름` / `## 제목` / `제목: 이름` — leading bullets, bold, and
# heading markers are all optional.
_LABEL_LINE = re.compile(
    r"^\s*(?:[-*+]\s*|#{1,6}\s*)?\*{0,2}\s*(?P<label>[^:：\n]{1,24}?)\s*\*{0,2}\s*[:：]\s*(?P<value>.*)$"
)
_HEADING = re.compile(r"^\s*#{1,6}\s*(?P<text>.+?)\s*$")


def _canonical_field(label: str) -> str | None:
    norm = label.strip().strip("*").strip().lower()
    for field, aliases in _LABEL_PATTERNS.items():
        for alias in aliases:
            if norm == alias or norm.startswith(alias):
                return field
    return None


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
    return slug[:40] or fallback


def option_id_for(agent: str, *, batch: int, seat: int) -> str:
    """Stable option id.

    Keyed by the batch that produced it and the agent seat — never by position
    in the options list, so re-ordering or re-rendering does not move a user's
    selection to a different candidate (§4.1).
    """
    return f"opt-{max(0, int(batch))}-{_slug(agent, f'seat{max(0, int(seat))}')}"


def parse_idea_option(text: str, *, option_id: str, agent: str = "") -> dict[str, Any]:
    """Parse one agent reply into a comparable option.

    Returns the structured fields it could read. When nothing recognizable is
    present the raw reply is preserved together with ``parse_error`` — a failed
    parse must never silently drop a candidate.
    """
    from agent_lab.room.context.ideation_quality import contract_quality, sanitize_ideation_text, unverified_repo_claims

    raw_body = (text or "").strip()
    body, removed_meta = sanitize_ideation_text(raw_body)
    option: dict[str, Any] = {"id": option_id, "agent": str(agent or "")}
    if not body:
        option["raw"] = raw_body
        option["parse_error"] = "empty_reply"
        option["quality"] = contract_quality(option, meta_removed=removed_meta)
        return option

    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        match = _LABEL_LINE.match(line)
        field = _canonical_field(match.group("label")) if match else None
        if field:
            current = field
            found.setdefault(field, [])
            # `- **제목:** 이름` puts the closing `**` after the colon.
            value = match.group("value").strip().lstrip("*").strip()
            if value:
                found[field].append(value)
            continue
        if current and line.strip():
            if _HEADING.match(line):
                current = None
                continue
            found[current].append(line.strip())

    for field, lines in found.items():
        option[field] = "\n".join(lines).strip()

    if not option.get("title"):
        heading = next((_HEADING.match(ln) for ln in body.splitlines() if _HEADING.match(ln)), None)
        option["title"] = heading.group("text") if heading else body.splitlines()[0].strip()[:120]

    option["raw"] = raw_body
    option["quality"] = contract_quality(
        option,
        meta_removed=removed_meta,
        repo_claims=unverified_repo_claims(body),
    )
    if removed_meta:
        option["meta_removed"] = removed_meta
    if not any(option.get(f) for f in ("principle", "usage", "difference", "tradeoff", "first_experiment")):
        option["parse_error"] = "no_recognized_sections"
    return option


def build_idea_options(replies: list[Any], *, batch: int) -> list[dict[str, Any]]:
    """Structured options for one exploration batch, capped like the legacy list."""
    options: list[dict[str, Any]] = []
    for seat, reply in enumerate(replies):
        content = _reply_field(reply, "content", "text", "message").strip()
        if not content:
            continue
        agent = _reply_field(reply, "agent", "role", "name")
        options.append(
            parse_idea_option(
                content,
                option_id=option_id_for(agent, batch=batch, seat=seat),
                agent=agent,
            )
        )
        if len(options) >= MAX_DIVERGENCE_OPTIONS:
            break
    return options
