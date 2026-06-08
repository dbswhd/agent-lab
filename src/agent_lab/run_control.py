"""Cooperative cancel + single-flight run lock for room/classic runs."""

from __future__ import annotations

import subprocess
import threading
import time
import weakref
from typing import Any

_cancel = threading.Event()
_children_lock = threading.Lock()
_active_children: list[weakref.ReferenceType[Any]] = []
_cursor_runs_lock = threading.Lock()
_active_cursor_runs: list[weakref.ReferenceType[Any]] = []
_run_lock = threading.Lock()
_run_active = 0
_run_started_at: float | None = None
RUN_LOCK_STALE_SEC = 600


class RoomRunCancelled(Exception):
    """Raised when the user requests stop before the next agent call."""


def clear_cancel() -> None:
    _cancel.clear()


def register_child_process(proc: subprocess.Popen[Any]) -> None:
    with _children_lock:
        _active_children.append(weakref.ref(proc))


def unregister_child_process(proc: subprocess.Popen[Any]) -> None:
    with _children_lock:
        _active_children[:] = [
            ref
            for ref in _active_children
            if ref() is not None and ref() is not proc
        ]


def register_cursor_run(run: Any) -> None:
    """Register an in-flight Cursor SDK Run for cancel_run on stop."""
    with _cursor_runs_lock:
        _active_cursor_runs.append(weakref.ref(run))


def unregister_cursor_run(run: Any) -> None:
    with _cursor_runs_lock:
        _active_cursor_runs[:] = [
            ref
            for ref in _active_cursor_runs
            if ref() is not None and ref() is not run
        ]


def _terminate_subprocess_children() -> int:
    killed = 0
    with _children_lock:
        refs = list(_active_children)
    for ref in refs:
        proc = ref()
        if proc is None or proc.poll() is not None:
            continue
        try:
            proc.kill()
            proc.wait(timeout=5)
            killed += 1
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except OSError:
                pass
    with _children_lock:
        _active_children.clear()
    return killed


def _cancel_cursor_runs() -> int:
    cancelled = 0
    with _cursor_runs_lock:
        refs = list(_active_cursor_runs)
    for ref in refs:
        run = ref()
        if run is None:
            continue
        try:
            run.cancel()
            cancelled += 1
        except Exception:
            pass
    with _cursor_runs_lock:
        _active_cursor_runs.clear()
    return cancelled


def terminate_active_children() -> int:
    """Kill CLI subprocesses + cancel Cursor SDK runs (Track D — ⌘. stop)."""
    return _cancel_cursor_runs() + _terminate_subprocess_children()


def request_cancel() -> int:
    _cancel.set()
    return terminate_active_children()


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
