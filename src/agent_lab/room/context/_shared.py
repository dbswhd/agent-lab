"""Shared types and helpers for room context assembly."""

from __future__ import annotations

import os
from typing import Protocol


class MessageLike(Protocol):
    role: str
    agent: str | None
    content: str
    parallel_round: int | None


# Backward-compatible alias for imports/tests.
_MessageLike = MessageLike


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def message_chars(msgs: list[MessageLike]) -> int:
    return sum(len(m.content) + 64 for m in msgs)
