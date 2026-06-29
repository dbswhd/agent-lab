"""Chat visibility channels (human vs peer) for multi-agent rooms."""

from __future__ import annotations

import re
from typing import Any, Literal

ChatVisibility = Literal["human", "peer"]

PEER_HEADER_ECHO = re.compile(r"^\[이번 턴\s*·\s*동료 발화\]", re.I)

_SDK_DEBUG_LINE = re.compile(
    r"(?:prepare_turn_policy|assign_task_owners|TurnPolicyEngine\.resolve)",
    re.I,
)
_SDK_BOILERPLATE = re.compile(r"^\s*I am ready to act\b", re.I)

DEFAULT_VISIBILITY: ChatVisibility = "human"


def normalize_visibility(raw: str | None) -> ChatVisibility:
    v = (raw or DEFAULT_VISIBILITY).strip().lower()
    return "peer" if v == "peer" else "human"


def is_peer_visibility(visibility: str | None) -> bool:
    return normalize_visibility(visibility) == "peer"


def message_visibility(
    *,
    role: str,
    content: str,
    explicit: str | None = None,
) -> ChatVisibility:
    if explicit:
        return normalize_visibility(explicit)
    if role == "user":
        return "human"
    if role == "agent" and PEER_HEADER_ECHO.search((content or "").strip()):
        return "peer"
    return "human"


def strip_peer_header_echo(content: str) -> str:
    """Drop a leading echoed ``[이번 턴 · 동료 발화]`` header that some agents
    prepend to their reply.

    Without this, :func:`message_visibility` marks the whole reply peer-only and
    hides the agent's real content from the human transcript (the agent appears
    to "disappear"). Returns the original content if stripping leaves nothing
    (a pure echo), so genuine echo-only noise still gets hidden.
    """
    text = content or ""
    match = PEER_HEADER_ECHO.match(text.lstrip())
    if not match:
        return content
    rest = text.lstrip()[match.end() :].lstrip(" :·\t").lstrip()
    return rest if rest.strip() else content


def strip_sdk_internal_monologue(content: str) -> str:
    """Remove Cursor/SDK debug monologue lines leaked into human transcript."""
    text = content or ""
    if not text.strip():
        return content
    kept: list[str] = []
    for line in text.splitlines():
        if _SDK_DEBUG_LINE.search(line):
            continue
        if _SDK_BOILERPLATE.match(line.strip()):
            continue
        kept.append(line)
    result = "\n".join(kept).strip()
    if not result and _SDK_BOILERPLATE.search(text):
        return ""
    return result if result else content


def filter_messages_for_human(
    messages: list[Any],
    *,
    include_peer: bool = False,
) -> list[Any]:
    if include_peer:
        return list(messages)
    out: list[Any] = []
    for m in messages:
        vis = getattr(m, "visibility", None)
        if vis is None:
            vis = message_visibility(
                role=getattr(m, "role", ""),
                content=getattr(m, "content", "") or "",
            )
        if is_peer_visibility(vis):
            continue
        out.append(m)
    return out
