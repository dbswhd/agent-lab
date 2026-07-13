"""Durable crash-recovery for the Mission ``ActivityQueue`` (F9 follow-up).

Mirrors ``agent_lab.crash_recovery`` (G3, legacy merge recovery) for the newer
Mission side-effect queue. ``ActivityQueue.recover()`` is the idempotent,
per-session primitive; this module is the orchestration layer that scans every
session under a sessions root and calls it, the same relationship
``reconcile_crashed_merges`` has to per-execution reconciliation.

Two call sites, one function, single-flight protected:

- ``_api_startup()`` calls ``recover_activity_queue(reason="startup")`` once,
  blocking, before the process starts serving — orphaned/stale activities are
  reconciled before anything else touches the queue.
- ``scheduler_tick()`` calls it too, but only when ``recovery_due()`` says the
  configured interval has elapsed, and non-blocking — if a concurrent scan
  (the startup call, or another tick) already holds the lock, this tick skips
  rather than waiting, so a slow scan never stacks up duplicate work.

The lock is a plain ``fcntl.flock`` on a dedicated file under the sessions
root (not a DB — this project has none), so it also serializes multiple
processes sharing the same sessions directory, not just threads within one.
"""

from __future__ import annotations

import fcntl
import json
import time
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from agent_lab.env_flags import env_bool

_DEFAULT_INTERVAL_S = 300
_STATE_FILENAME = ".activity-queue-recovery-state.json"
_LOCK_FILENAME = ".activity-queue-recovery.lock"


def activity_queue_recovery_enabled() -> bool:
    """Opt-out via ``AGENT_LAB_ACTIVITY_QUEUE_RECOVERY=0`` (default on)."""
    return env_bool("AGENT_LAB_ACTIVITY_QUEUE_RECOVERY", default=True)


def activity_recovery_interval_s() -> int:
    import os

    raw = (os.getenv("AGENT_LAB_ACTIVITY_RECOVERY_INTERVAL_S") or "").strip()
    try:
        return max(30, min(int(raw), 3600))
    except ValueError:
        return _DEFAULT_INTERVAL_S


def _state_path(sessions_root: Path) -> Path:
    return sessions_root / _STATE_FILENAME


def _lock_path(sessions_root: Path) -> Path:
    return sessions_root / _LOCK_FILENAME


def _load_state(sessions_root: Path) -> dict[str, Any]:
    path = _state_path(sessions_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(sessions_root: Path, state: dict[str, Any]) -> None:
    path = _state_path(sessions_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def recovery_due(sessions_root: Path, *, now: float, interval_s: int | None = None) -> bool:
    last = _load_state(sessions_root).get("last_run_at")
    if not isinstance(last, (int, float)):
        return True
    return (now - last) >= (interval_s if interval_s is not None else activity_recovery_interval_s())


@contextmanager
def _flock(path: Path, *, blocking: bool) -> Iterator[bool]:
    """Yield ``True`` if the exclusive lock was acquired, ``False`` otherwise.

    Blocking mode waits (used by the eager startup call); non-blocking mode
    returns immediately if another scan already holds the lock (used by the
    periodic tick, so a slow scan never causes ticks to pile up waiting).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(stream.fileno(), flags)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _scan_sessions(sessions_root: Path, *, now: float) -> dict[str, Any]:
    from agent_lab.mission.activity_queue import ActivityQueue

    scanned = 0
    errors = 0
    action_counts: dict[str, int] = {}
    sessions: list[dict[str, Any]] = []
    for folder in sorted(sessions_root.iterdir()):
        if not folder.is_dir() or folder.name.startswith((".", "_")):
            continue
        queue_path = folder / ".agent-lab" / "activities.json"
        if not queue_path.is_file():
            continue
        scanned += 1
        try:
            decisions = ActivityQueue.for_session(folder).recover(now=now)
        except Exception as exc:  # one bad session must not abort the scan
            errors += 1
            sessions.append({"session": folder.name, "error": str(exc)[:200]})
            continue
        if decisions:
            for decision in decisions:
                action_counts[decision.action.value] = action_counts.get(decision.action.value, 0) + 1
            sessions.append({"session": folder.name, "count": len(decisions)})
    return {"scanned": scanned, "errors": errors, "actions": action_counts, "sessions": sessions}


def recover_activity_queue(
    sessions_root: Path | None = None,
    *,
    reason: str,
    now: float | None = None,
    blocking: bool = True,
) -> dict[str, Any]:
    """Idempotent, single-flight-protected scan. Never raises.

    ``reason`` is ``"startup"`` or ``"periodic"`` (or a test-supplied label) —
    recorded in the returned summary and the on-disk state marker for the
    caller to log/inspect, not otherwise load-bearing.
    """
    now_val = now if now is not None else time.time()
    summary: dict[str, Any] = {"reason": reason, "at": now_val, "enabled": True, "locked_out": False}
    try:
        if not activity_queue_recovery_enabled():
            summary["enabled"] = False
            return summary
        root = sessions_root
        if root is None:
            from agent_lab.session.paths import active_sessions_dir

            root = active_sessions_dir()
        if root is None or not root.is_dir():
            summary.update({"scanned": 0, "errors": 0, "actions": {}, "sessions": []})
            return summary
        with _flock(_lock_path(root), blocking=blocking) as acquired:
            if not acquired:
                summary["locked_out"] = True
                return summary
            scan = _scan_sessions(root, now=now_val)
            summary.update(scan)
            _save_state(root, {"last_run_at": now_val, "last_reason": reason, "last_summary": scan})
            return summary
    except Exception as exc:  # never raise — callers (startup, scheduler tick) must not be blocked
        summary["errors"] = summary.get("errors", 0) + 1
        summary["fatal_error"] = str(exc)[:200]
        return summary
