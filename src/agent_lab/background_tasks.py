"""Fire-and-forget background task manager (Phase 3).

Background tasks are independent of the Room run lock — they run in a
separate ThreadPoolExecutor and do not interact with run_control.py.
This lets a dev server, build script, or long-running watcher coexist
with normal room turns.

Tasks are session-scoped and stored in:
  sessions/{id}/bg_tasks/{task_id}.json   ← status snapshot
  sessions/{id}/bg_tasks/{task_id}.log    ← stdout/stderr (line-buffered)
"""

from __future__ import annotations

import json
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from agent_lab.subprocess_env import subprocess_env
from agent_lab.time_utils import utc_now_iso as _now_iso

TaskStatus = Literal["queued", "running", "done", "failed", "cancelled"]

_BG_DIR = "bg_tasks"
_POOL_SIZE = 6


@dataclass
class BgTask:
    task_id: str
    session_id: str
    label: str
    command: list[str]
    cwd: str
    status: TaskStatus = "queued"
    created_at: str = field(default_factory=_now_iso)
    started_at: str | None = None
    ended_at: str | None = None
    exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskManager:
    """Singleton that owns the ThreadPoolExecutor and task registry."""

    def __init__(self) -> None:
        self._tasks: dict[str, BgTask] = {}
        self._procs: dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=_POOL_SIZE, thread_name_prefix="bg-task")

    # ── public API ────────────────────────────────────────────────────────────

    def submit(
        self,
        session_folder: Path,
        label: str,
        command: list[str],
        cwd: str | None = None,
    ) -> BgTask:
        task_id = uuid.uuid4().hex[:8]
        session_id = session_folder.name
        resolved_cwd = cwd or str(session_folder)

        task = BgTask(
            task_id=task_id,
            session_id=session_id,
            label=label,
            command=command,
            cwd=resolved_cwd,
        )
        _ensure_bg_dir(session_folder).mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._tasks[task_id] = task
        _save_status(session_folder, task)
        self._pool.submit(self._run, task_id, session_folder)
        return task

    def get(self, task_id: str) -> BgTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_for_session(self, session_id: str) -> list[BgTask]:
        with self._lock:
            return sorted(
                [t for t in self._tasks.values() if t.session_id == session_id],
                key=lambda t: t.created_at,
                reverse=True,
            )

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task.status not in ("queued", "running"):
                return False
            task.status = "cancelled"
            task.ended_at = _now_iso()
            proc = self._procs.get(task_id)

        if proc is not None:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()
                except OSError:
                    pass
        return True

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=cancel_futures)

    def read_log(self, session_folder: Path, task_id: str, offset: int = 0) -> list[dict[str, Any]]:
        log_path = _log_path(session_folder, task_id)
        if not log_path.is_file():
            return []
        lines = []
        with log_path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i < offset:
                    continue
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        lines.append({"text": line})
        return lines

    # ── internal ─────────────────────────────────────────────────────────────

    def _run(self, task_id: str, session_folder: Path) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status == "cancelled":
                return
            task.status = "running"
            task.started_at = _now_iso()
        _save_status(session_folder, task)

        log = _log_path(session_folder, task_id)
        try:
            proc = subprocess.Popen(
                task.command,
                cwd=task.cwd,
                env=subprocess_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            with self._lock:
                self._procs[task_id] = proc

            with log.open("a", encoding="utf-8") as lf:
                for line in proc.stdout or []:
                    entry = json.dumps({"text": line.rstrip("\n")}, ensure_ascii=False)
                    lf.write(entry + "\n")
                    lf.flush()

            proc.wait()
            exit_code = proc.returncode
        except Exception as exc:
            exit_code = -1
            with log.open("a", encoding="utf-8") as lf:
                lf.write(json.dumps({"text": f"[error] {exc}", "stream": "err"}) + "\n")
        finally:
            with self._lock:
                self._procs.pop(task_id, None)

        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            if task.status == "cancelled":
                pass  # already marked
            elif exit_code == 0:
                task.status = "done"
            else:
                task.status = "failed"
            task.exit_code = exit_code
            task.ended_at = _now_iso()
        _save_status(session_folder, task)


# ── module-level singleton ────────────────────────────────────────────────────

_manager: TaskManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> TaskManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = TaskManager()
    return _manager


# ── helpers ───────────────────────────────────────────────────────────────────


def _ensure_bg_dir(session_folder: Path) -> Path:
    p = session_folder / _BG_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _log_path(session_folder: Path, task_id: str) -> Path:
    return session_folder / _BG_DIR / f"{task_id}.log"


def _status_path(session_folder: Path, task_id: str) -> Path:
    return session_folder / _BG_DIR / f"{task_id}.json"


def _save_status(session_folder: Path, task: BgTask) -> None:
    path = _status_path(session_folder, task.task_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(task.to_dict(), indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def load_persisted_tasks(session_folder: Path, manager: TaskManager) -> None:
    """On startup, restore completed/failed tasks from disk (in-memory only)."""
    bg_dir = session_folder / _BG_DIR
    if not bg_dir.is_dir():
        return
    for status_file in sorted(bg_dir.glob("*.json")):
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            task = BgTask(**{k: data[k] for k in BgTask.__dataclass_fields__ if k in data})
            if task.status in ("queued", "running"):
                task.status = "failed"
                task.ended_at = task.ended_at or _now_iso()
            with manager._lock:
                if task.task_id not in manager._tasks:
                    manager._tasks[task.task_id] = task
        except Exception:
            pass
