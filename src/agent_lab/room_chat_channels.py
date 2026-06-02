"""Chat visibility channels (human vs peer) for multi-agent rooms."""

from __future__ import annotations

import re
from typing import Any, Literal

ChatVisibility = Literal["human", "peer"]

PEER_HEADER_ECHO = re.compile(r"^\[이번 턴\s*·\s*동료 발화\]", re.I)

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
