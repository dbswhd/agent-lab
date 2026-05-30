"""Cooperative cancel + single-flight run lock for room/classic runs."""

from __future__ import annotations

import threading
import time

_cancel = threading.Event()
_run_lock = threading.Lock()
_run_active = 0
_run_started_at: float | None = None
RUN_LOCK_STALE_SEC = 600


class RoomRunCancelled(Exception):
    """Raised when the user requests stop before the next agent call."""


def clear_cancel() -> None:
    _cancel.clear()


def request_cancel() -> None:
    _cancel.set()


def is_cancelled() -> bool:
    return _cancel.is_set()


def check_cancelled() -> None:
    if _cancel.is_set():
        raise RoomRunCancelled("run cancelled by user")


def run_lock_status() -> dict[str, object]:
    locked = _run_lock.locked()
    age_sec: float | None = None
    if locked and _run_started_at is not None:
        age_sec = round(time.time() - _run_started_at, 1)
    return {
        "locked": locked,
        "active_workers": _run_active,
        "age_sec": age_sec,
    }


def force_reset_run_lock() -> None:
    global _run_active, _run_started_at
    _run_active = 0
    _run_started_at = None
    clear_cancel()
    while _run_lock.locked():
        try:
            _run_lock.release()
        except RuntimeError:
            break


def maybe_release_stale_run_lock(max_age_sec: float = RUN_LOCK_STALE_SEC) -> bool:
    """Release a run lock left behind by a crashed/disconnected stream."""
    global _run_active, _run_started_at
    if not _run_lock.locked():
        return False
    if _run_started_at is None:
        force_reset_run_lock()
        return True
    if time.time() - _run_started_at < max_age_sec:
        return False
    force_reset_run_lock()
    return True


def maybe_release_orphaned_run_lock() -> bool:
    """Release a lock with no active worker (crashed SSE generator)."""
    if not _run_lock.locked():
        return False
    if _run_active == 0:
        force_reset_run_lock()
        return True
    return maybe_release_stale_run_lock(max_age_sec=90)


def try_begin_run() -> bool:
    """Acquire the global single-flight run lock (worker thread only)."""
    global _run_active, _run_started_at
    maybe_release_stale_run_lock()
    if not _run_lock.acquire(blocking=False):
        return False
    _run_active += 1
    _run_started_at = time.time()
    clear_cancel()
    return True


def end_run() -> None:
    """Release the global run lock after worker completion."""
    global _run_active, _run_started_at
    _run_active = max(0, _run_active - 1)
    if _run_active == 0:
        _run_started_at = None
    try:
        _run_lock.release()
    except RuntimeError:
        force_reset_run_lock()
