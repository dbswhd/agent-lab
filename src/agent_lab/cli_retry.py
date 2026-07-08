"""Shared retry policy for subscription CLI bridges."""

from __future__ import annotations

import os
import random
import re
import time
from collections.abc import Callable
from typing import TypeVar

from agent_lab.env_flags import env_bool

T = TypeVar("T")

_RETRYABLE_PATTERNS = (
    r"\b429\b",
    r"rate limit",
    r"\btimeout\b",
    r"timed out",
    r"connection refused",
    r"temporarily unavailable",
    r"overloaded",
    r"exit(?: code)? 52\b",
    r"exit 52\b",
)

_NON_RETRYABLE_PATTERNS = (
    r"auth(?:entication)?",
    r"credit balance",
    r"invalid api key",
    r"permission denied",
    r"empty output",
    r"returned empty output",
)


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def is_retryable(exc_or_stderr: object) -> bool:
    """Return True for transient CLI failures and False for deterministic failures."""
    text = str(exc_or_stderr or "").strip().lower()
    if not text:
        return False
    if any(re.search(pat, text) for pat in _NON_RETRYABLE_PATTERNS):
        return False
    return any(re.search(pat, text) for pat in _RETRYABLE_PATTERNS)


def retry_max_attempts(*, room_turn: bool) -> int:
    if env_bool("AGENT_LAB_CLI_RETRY_ROOM_ONLY") and not room_turn:
        return 1
    return _env_int("AGENT_LAB_CLI_RETRY_MAX", 3)


def retry_base_delay_sec() -> float:
    return _env_float("AGENT_LAB_CLI_RETRY_BASE_SEC", 2.0)


def retry_attempts(exc: BaseException) -> int:
    return int(getattr(exc, "agent_lab_retry_attempts", 1) or 1)


def retryable_failure(exc: BaseException) -> bool:
    raw = getattr(exc, "agent_lab_retryable", None)
    if raw is not None:
        return bool(raw)
    return is_retryable(exc)


def _mark_failure(exc: BaseException, *, attempts: int, retryable: bool) -> None:
    try:
        setattr(exc, "agent_lab_retry_attempts", attempts)
        setattr(exc, "agent_lab_retryable", retryable)
    except Exception:
        pass


def retry_call(
    fn: Callable[[], T],
    *,
    max_attempts: int | None = None,
    base_delay_sec: float | None = None,
    jitter: bool = True,
    on_retry_label: Callable[[int, int, str], None] | None = None,
) -> T:
    """Run `fn` with the shared transient CLI retry policy."""
    attempts = max(1, int(max_attempts or 1))
    base_delay = retry_base_delay_sec() if base_delay_sec is None else base_delay_sec
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            # A raiser may already know its failure is decisive (e.g. a genuine
            # stall, not a transient rate limit) and pre-mark agent_lab_retryable —
            # respect that instead of re-guessing from the message text, since a
            # message can accidentally contain a retryable-looking word like
            # "timeout" while describing a non-transient stall.
            retryable = retryable_failure(exc)
            _mark_failure(exc, attempts=attempt, retryable=retryable)
            last_exc = exc
            if not retryable or attempt >= attempts:
                raise
            next_attempt = attempt + 1
            if on_retry_label:
                on_retry_label(next_attempt, attempts, str(exc))
            delay = base_delay * (2 ** (attempt - 1))
            if jitter and delay > 0:
                delay += random.uniform(0, delay * 0.25)
            if delay > 0:
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc
