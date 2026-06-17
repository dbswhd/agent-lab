"""Read/write run.json without a full room turn."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from weakref import WeakValueDictionary

_LOCK_GUARD = threading.Lock()
_FOLDER_LOCKS: WeakValueDictionary[str, threading.Lock] = WeakValueDictionary()


def _folder_lock(folder: Path) -> threading.Lock:
    key = str(folder.resolve())
    with _LOCK_GUARD:
        lock = _FOLDER_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _FOLDER_LOCKS[key] = lock
        return lock


def read_run_meta(folder: Path) -> dict[str, Any]:
    run_path = folder / "run.json"
    if not run_path.is_file():
        return {}
    for attempt in range(4):
        try:
            raw = run_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = run_path.read_text(encoding="utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            if attempt >= 3:
                return {}
            from agent_lab.backoff_policy import wait as _backoff_wait

            _backoff_wait(attempt + 1, base_sec=0.01)
    return {}


_EPHEMERAL_RUN_KEYS = frozenset(
    {
        "_session_folder",
        "_session_id",
        "_active_turn_mode",
        "_active_synthesize",
        "_active_consensus",
        "_turn_category",
        "_escalation_harvest_keys",
    }
)


def persist_run_meta(run: dict[str, Any]) -> dict[str, Any]:
    """Drop in-memory-only keys before writing run.json."""
    return {k: v for k, v in run.items() if k not in _EPHEMERAL_RUN_KEYS}


def write_run_meta(folder: Path, run: dict[str, Any]) -> None:
    from agent_lab.run_schema import validate_run

    validate_run(run)
    payload = json.dumps(persist_run_meta(run), indent=2, ensure_ascii=False) + "\n"
    path = folder / "run.json"
    tmp = path.with_suffix(".json.tmp")
    with _folder_lock(folder):
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)


def patch_run_meta(
    folder: Path,
    updater: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    from agent_lab.run_schema import validate_run

    with _folder_lock(folder):
        run = read_run_meta(folder)
        updated = updater(run)
        validate_run(updated)
        payload = json.dumps(persist_run_meta(updated), indent=2, ensure_ascii=False) + "\n"
        path = folder / "run.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    return updated


def completed_step_key(*, human_turn: int, parallel_round: int, agent: str) -> str:
    return f"turn_{human_turn}_round_{parallel_round}_{agent.strip().lower()}"


def get_completed_step(
    run: dict[str, Any],
    *,
    human_turn: int,
    parallel_round: int,
    agent: str,
) -> dict[str, Any] | None:
    key = completed_step_key(
        human_turn=human_turn,
        parallel_round=parallel_round,
        agent=agent,
    )
    for step in run.get("completed_steps") or []:
        if step.get("step") == key:
            return step
    return None


def record_completed_step(
    folder: Path,
    *,
    human_turn: int,
    parallel_round: int,
    agent: str,
    content: str,
    envelope: dict[str, Any] | None = None,
    msg_idx: int | None = None,
    run_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = completed_step_key(
        human_turn=human_turn,
        parallel_round=parallel_round,
        agent=agent,
    )
    entry: dict[str, Any] = {
        "step": key,
        "human_turn": human_turn,
        "parallel_round": parallel_round,
        "agent": agent.strip().lower(),
        "ts": datetime.now(timezone.utc).isoformat(),
        "content": content,
    }
    if envelope is not None:
        entry["envelope"] = envelope
    if msg_idx is not None:
        entry["msg_idx"] = msg_idx

    def _upsert(run: dict[str, Any]) -> dict[str, Any]:
        steps = [s for s in (run.get("completed_steps") or []) if s.get("step") != key]
        steps.append(entry)
        run["completed_steps"] = steps
        return run

    updated = patch_run_meta(folder, _upsert)
    if run_meta is not None:
        run_meta["completed_steps"] = updated.get("completed_steps")
    return updated


def clear_completed_steps_for_human_turn(folder: Path, human_turn: int) -> None:
    def _clear(run: dict[str, Any]) -> dict[str, Any]:
        steps = [s for s in (run.get("completed_steps") or []) if int(s.get("human_turn") or 0) != human_turn]
        run["completed_steps"] = steps
        return run

    patch_run_meta(folder, _clear)


def append_hook_run(
    folder: Path | None,
    record: dict[str, Any],
    *,
    run_meta: dict[str, Any] | None = None,
) -> None:
    """Append one hook run record to run.json (and optional in-memory run_meta)."""
    if folder is None:
        if run_meta is not None:
            runs = list(run_meta.get("hook_runs") or [])
            runs.append(record)
            run_meta["hook_runs"] = runs[-200:]
        return

    def _append(run: dict[str, Any]) -> dict[str, Any]:
        runs = list(run.get("hook_runs") or [])
        runs.append(record)
        run["hook_runs"] = runs[-200:]
        return run

    updated = patch_run_meta(folder, _append)
    if run_meta is not None:
        run_meta["hook_runs"] = updated.get("hook_runs")
