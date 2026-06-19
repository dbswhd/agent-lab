"""In-process burst limiter for bare GET /api/health polls."""

from __future__ import annotations

import os
import threading
import time

from fastapi import HTTPException

_DEFAULT_MAX = 30
_DEFAULT_WINDOW_SEC = 1.0


class _SlidingWindowLimiter:
    def __init__(self, *, max_calls: int, window_sec: float) -> None:
        self._max = max_calls
        self._window = window_sec
        self._lock = threading.Lock()
        self._timestamps: list[float] = []

    def check(self) -> None:
        now = time.monotonic()
        with self._lock:
            cutoff = now - self._window
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            if len(self._timestamps) >= self._max:
                raise HTTPException(status_code=429, detail="Too Many Requests")
            self._timestamps.append(now)

    def reset(self) -> None:
        with self._lock:
            self._timestamps.clear()


def _limiter() -> _SlidingWindowLimiter:
    max_calls = int(os.getenv("AGENT_LAB_HEALTH_RATE_LIMIT_MAX", str(_DEFAULT_MAX)))
    window_sec = float(os.getenv("AGENT_LAB_HEALTH_RATE_LIMIT_WINDOW_SEC", str(_DEFAULT_WINDOW_SEC)))
    return _SlidingWindowLimiter(max_calls=max_calls, window_sec=window_sec)


_health_limiter: _SlidingWindowLimiter | None = None


def _get_limiter() -> _SlidingWindowLimiter:
    global _health_limiter
    if _health_limiter is None:
        _health_limiter = _limiter()
    return _health_limiter


def enforce_health_burst_limit(
    *,
    probe_bridge: bool = False,
    probe_preflight: bool = False,
    session_id: str | None = None,
) -> None:
    """Rate-limit only bare health polls; probe/session queries stay unlimited."""
    if probe_bridge or probe_preflight or session_id:
        return
    _get_limiter().check()


def reset_health_rate_limit_for_tests() -> None:
    global _health_limiter
    _health_limiter = _limiter()
