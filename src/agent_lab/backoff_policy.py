"""Central retry backoff policy for agent-lab runtime and CLI bridges."""

from __future__ import annotations

import os
import time


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(0.0, value)


sleep_base_sec = _env_float("AGENT_LAB_BACKOFF_BASE_SEC", 2.0)


def next_backoff(attempt: int, base_sec: float | None = None) -> float:
    """Linear backoff derived from attempt index (1-based)."""
    base = float(base_sec if base_sec is not None else sleep_base_sec)
    attempt_index = max(attempt, 1)
    return base * attempt_index


def wait(attempt: int, base_sec: float | None = None) -> None:
    """Sleep using the shared linear backoff policy."""
    delay = next_backoff(attempt=attempt, base_sec=base_sec)
    if delay > 0:
        time.sleep(delay)
