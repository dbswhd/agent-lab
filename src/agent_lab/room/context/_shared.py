"""Shared types and helpers for room context assembly."""

from __future__ import annotations

from typing import Protocol

from agent_lab.env_flags import env_bool

__all__ = ["MessageLike", "_MessageLike", "env_bool", "message_chars"]


class MessageLike(Protocol):
    role: str
    agent: str | None
    content: str
    parallel_round: int | None


# Backward-compatible alias for imports/tests.
_MessageLike = MessageLike


def message_chars(msgs: list[MessageLike]) -> int:
    return sum(len(m.content) + 64 for m in msgs)
