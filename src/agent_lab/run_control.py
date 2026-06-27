"""Cooperative cancel + cross-process single-flight run lock for room/classic runs."""

from __future__ import annotations

import contextvars
import fcntl
import json
import os
import subprocess
import threading
import time
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from agent_lab.app_config import config_dir

_cancel = threading.Event()
_session_cancel_lock = threading.Lock()
_session_cancels: dict[str, threading.Event] = {}
_run_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_session_id", default=None)

_children_lock = threading.Lock()
_active_children: list[tuple[weakref.ReferenceType[Any], str | None]] = []
_cursor_runs_lock = threading.Lock()
_active_cursor_runs: list[weakref.ReferenceType[Any]] = []

# In-process guard + worker accounting (pairs with fcntl file lock below).
_run_lock = threading.Lock()
_run_active = 0
_run_started_at: float | None = None
_run_context_lock = threading.Lock()
_run_context: dict[str, Any] = {}

# Cross-process file lock (~/.agent-lab/run.lock). Future: AGENT_LAB_RUN_LOCK_BACKEND=redis.
_lock_fd: int | None = None
_lock_meta_path: Path | None = None

RUN_LOCK_STALE_SEC = 600

_RUN_KIND_LABELS = {
    "room": "Room turn",
    "retry": "Retry agents",
    "execute": "Plan execute",
    "mission": "Mission loop",
    "classic": "Classic run",
}


def _default_run_label(run_kind: str) -> str:
    return _RUN_KIND_LABELS.get(run_kind, run_kind.replace("_", " ").title() or "Run")


class RoomRunCancelled(Exception):
    """Raised when the user requests stop before the next agent call."""


def _lock_paths() -> tuple[Path, Path]:
    base = config_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base / "run.lock", base / "run.lock.meta"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_lock_meta() -> dict[str, Any]:
    _, meta_path = _lock_paths()
    if not meta_path.is_file():
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_lock_meta(meta: dict[str, Any]) -> None:
    _, meta_path = _lock_paths()
    tmp = meta_path.with_suffix(".meta.tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(meta_path)


def _clear_lock_meta() -> None:
    _, meta_path = _lock_paths()
    try:
        meta_path.unlink(missing_ok=True)
    except OSError:
        pass


def _file_lock_held() -> bool:
    return _lock_fd is not None


def _try_acquire_file_lock() -> bool:
    global _lock_fd, _lock_meta_path
    lock_path, meta_path = _lock_paths()
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        meta = _read_lock_meta()
        holder_pid = int(meta.get("pid") or 0)
        if holder_pid and not _pid_alive(holder_pid):
            # Holder died; flock should be released — retry once.
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                return False
        else:
            return False
    _lock_fd = fd
    _lock_meta_path = meta_path
    meta_payload = {"pid": os.getpid(), "started_at": time.time()}
    with _run_context_lock:
        if _run_context:
            meta_payload.update(
                {
                    "session_id": _run_context.get("session_id"),
                    "run_kind": _run_context.get("run_kind"),
                    "label": _run_context.get("label"),
                }
            )
    _write_lock_meta(meta_payload)
    return True


def _release_file_lock() -> None:
    global _lock_fd, _lock_meta_path
    if _lock_fd is not None:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            os.close(_lock_fd)
        except OSError:
            pass
        _lock_fd = None
        _lock_meta_path = None
    _clear_lock_meta()


def set_run_session_id(session_id: str | None) -> contextvars.Token[str | None]:
    """Bind the current worker to a session for scoped cancel checks."""
    return _run_session_id.set(session_id)


def reset_run_session_id(token: contextvars.Token[str | None]) -> None:
    _run_session_id.reset(token)


def current_run_session_id() -> str | None:
    return _run_session_id.get()


def _session_cancel_event(session_id: str) -> threading.Event:
    with _session_cancel_lock:
        ev = _session_cancels.get(session_id)
        if ev is None:
            ev = threading.Event()
            _session_cancels[session_id] = ev
        return ev


def clear_cancel(session_id: str | None = None) -> None:
    if session_id:
        with _session_cancel_lock:
            ev = _session_cancels.pop(session_id, None)
        if ev is not None:
            ev.clear()
        return
    _cancel.clear()
    with _session_cancel_lock:
        for ev in _session_cancels.values():
            ev.clear()
        _session_cancels.clear()


def register_child_process(proc: subprocess.Popen[Any], session_id: str | None = None) -> None:
    sid = session_id if session_id is not None else current_run_session_id()
    with _children_lock:
        _active_children.append((weakref.ref(proc), sid))


def unregister_child_process(proc: subprocess.Popen[Any]) -> None:
    with _children_lock:
        _active_children[:] = [
            (ref, sid) for ref, sid in _active_children if ref() is not None and ref() is not proc
        ]


def register_cursor_run(run: Any) -> None:
    """Register an in-flight Cursor SDK Run for cancel_run on stop."""
    with _cursor_runs_lock:
        _active_cursor_runs.append(weakref.ref(run))


def unregister_cursor_run(run: Any) -> None:
    with _cursor_runs_lock:
        _active_cursor_runs[:] = [ref for ref in _active_cursor_runs if ref() is not None and ref() is not run]


def _terminate_subprocess_children(session_id: str | None = None) -> int:
    killed = 0
    with _children_lock:
        refs = list(_active_children)
    for ref, sid in refs:
        proc = ref()
        if proc is None or proc.poll() is not None:
            continue
        if session_id is not None and sid != session_id:
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
    if session_id is None:
        with _children_lock:
            _active_children.clear()
    else:
        with _children_lock:
            _active_children[:] = [
                (ref, sid)
                for ref, sid in _active_children
                if not (sid == session_id and (ref() is None or ref().poll() is not None))
            ]
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


def terminate_active_children(session_id: str | None = None) -> int:
    """Kill CLI subprocesses + cancel Cursor SDK runs (Track D — ⌘. stop)."""
    if session_id is None:
        return _cancel_cursor_runs() + _terminate_subprocess_children(None)
    return _terminate_subprocess_children(session_id)


def request_cancel(session_id: str | None = None) -> int:
    if session_id:
        _session_cancel_event(session_id).set()
        return terminate_active_children(session_id)
    _cancel.set()
    with _session_cancel_lock:
        for ev in _session_cancels.values():
            ev.set()
    return terminate_active_children(None)


def is_cancelled(session_id: str | None = None) -> bool:
    if _cancel.is_set():
        return True
    sid = session_id if session_id is not None else current_run_session_id()
    if sid:
        with _session_cancel_lock:
            ev = _session_cancels.get(sid)
        if ev is not None and ev.is_set():
            return True
    return False


def check_cancelled() -> None:
    if is_cancelled():
        raise RoomRunCancelled("run cancelled by user")


def run_lock_recovery_hint() -> dict[str, object]:
    """Structured recovery signal for a blocked run start (RecoveryStrip-friendly)."""
    status = run_lock_status()
    locked = bool(status.get("locked"))
    active_workers = int(status.get("active_workers") or 0)
    age_raw = status.get("age_sec")
    age_sec = age_raw if isinstance(age_raw, (int, float)) else None
    releasable = (not locked) or active_workers == 0 or (age_sec is not None and age_sec >= RUN_LOCK_STALE_SEC)
    if releasable:
        action = "release_lock: POST /api/room/runs/release-lock to clear the stale/orphaned lock, then retry."
    else:
        action = "wait_or_cancel: an active run is in progress — wait for it to finish or POST /api/room/runs/cancel."
    return {
        "locked": locked,
        "age_sec": age_sec,
        "active_workers": active_workers,
        "releasable": releasable,
        "action": action,
    }


def run_lock_status() -> dict[str, object]:
    locked = _run_lock.locked() or _file_lock_held()
    age_sec: float | None = None
    if locked and _run_started_at is not None:
        age_sec = round(time.time() - _run_started_at, 1)
    with _run_context_lock:
        ctx = dict(_run_context)
    meta = _read_lock_meta() if locked else {}
    session_id = ctx.get("session_id") or meta.get("session_id")
    run_kind = str(ctx.get("run_kind") or meta.get("run_kind") or "room")
    label = str(ctx.get("label") or meta.get("label") or _default_run_label(run_kind))
    return {
        "locked": locked,
        "active_workers": _run_active,
        "age_sec": age_sec,
        "session_id": session_id,
        "run_kind": run_kind,
        "label": label,
    }


def force_reset_run_lock() -> None:
    global _run_active, _run_started_at
    _run_active = 0
    _run_started_at = None
    with _run_context_lock:
        _run_context.clear()
    while _run_lock.locked():
        try:
            _run_lock.release()
        except RuntimeError:
            break
    _release_file_lock()


def maybe_release_stale_run_lock(max_age_sec: float = RUN_LOCK_STALE_SEC) -> bool:
    """Release a run lock left behind by a crashed/disconnected stream."""
    global _run_active, _run_started_at
    if not _run_lock.locked() and not _file_lock_held():
        return False
    if _run_started_at is None:
        force_reset_run_lock()
        return True
    if time.time() - _run_started_at < max_age_sec:
        meta = _read_lock_meta()
        holder_pid = int(meta.get("pid") or 0)
        if holder_pid and not _pid_alive(holder_pid):
            force_reset_run_lock()
            return True
        return False
    force_reset_run_lock()
    return True


def maybe_release_orphaned_run_lock() -> bool:
    """Release a lock with no active worker (crashed SSE generator)."""
    if not _run_lock.locked() and not _file_lock_held():
        return False
    if _run_active == 0:
        force_reset_run_lock()
        return True
    return maybe_release_stale_run_lock(max_age_sec=90)


def room_run_in_progress() -> bool:
    """True while a room/classic worker holds the global run lock."""
    return _run_active > 0


def try_begin_run(
    *,
    session_id: str | None = None,
    run_kind: str = "room",
    label: str | None = None,
) -> bool:
    """Acquire the global single-flight run lock (worker thread only)."""
    global _run_active, _run_started_at
    maybe_release_stale_run_lock()
    if not _run_lock.acquire(blocking=False):
        return False
    try:
        with _run_context_lock:
            _run_context.clear()
            _run_context.update(
                {
                    "session_id": session_id,
                    "run_kind": run_kind,
                    "label": label or _default_run_label(run_kind),
                }
            )
        if not _try_acquire_file_lock():
            with _run_context_lock:
                _run_context.clear()
            _run_lock.release()
            return False
    except Exception:
        with _run_context_lock:
            _run_context.clear()
        _run_lock.release()
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
        with _run_context_lock:
            _run_context.clear()
        _release_file_lock()
    try:
        _run_lock.release()
    except RuntimeError:
        force_reset_run_lock()


@contextmanager
def run_guard(
    *,
    session_id: str | None = None,
    run_kind: str = "room",
    label: str | None = None,
) -> Iterator[bool]:
    """Acquire run lock for background paths (execute / mission / retry)."""
    acquired = try_begin_run(session_id=session_id, run_kind=run_kind, label=label)
    if not acquired:
        yield False
        return
    token = set_run_session_id(session_id)
    try:
        yield True
    finally:
        reset_run_session_id(token)
        end_run()
