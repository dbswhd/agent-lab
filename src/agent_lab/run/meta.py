"""Read/write run.json without a full room turn."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable
from weakref import WeakValueDictionary

from agent_lab.time_utils import utc_now_iso
from agent_lab.env_flags import env_bool
from agent_lab.run.state import RunState, RunStateLike, RuntimeValidationError, validate_run_data

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


def stamp_run_meta(run_meta: RunStateLike, **fields: Any) -> RunStateLike:
    """In-memory field updates during a turn (F4-safe — avoids ``run_meta[``).

    Prefer this (or ``run_meta.update({...})``) over subscript assignment so
    ``tests/test_run_meta_write_discipline.py`` can ratchet the allowlist down.
    Disk writes still go through ``patch_run_meta`` / turn-end replay only.
    """
    if fields:
        run_meta.update(fields)
    return run_meta


def read_run_meta(folder: Path) -> RunState:
    run_path = folder / "run.json"
    if not run_path.is_file():
        return RunState.empty()
    for attempt in range(4):
        try:
            raw = run_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = run_path.read_text(encoding="utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return RunState.from_raw(parsed)
            return RunState.empty()
        except json.JSONDecodeError:
            if attempt >= 3:
                return RunState.empty()
            from agent_lab.backoff_policy import wait as _backoff_wait

            _backoff_wait(attempt + 1, base_sec=0.01)
        except RuntimeValidationError:
            return RunState.empty()
    return RunState.empty()


_EPHEMERAL_RUN_KEYS = frozenset(
    {
        "_session_folder",
        "_session_id",
        "_active_turn_mode",
        "_active_synthesize",
        "_active_consensus",
        "_turn_category",
        "_turn_roles",
        "_escalation_harvest_keys",
    }
)


def persist_run_meta(run: dict[str, Any] | RunState) -> dict[str, Any]:
    """Drop in-memory-only keys before writing run.json."""
    return {k: v for k, v in run.items() if k not in _EPHEMERAL_RUN_KEYS}


def _coerce_run_state(run: dict[str, Any] | RunState) -> RunState:
    if isinstance(run, RunState):
        validate_run_data(run)
        return run
    return RunState.from_raw(run)


def write_run_meta(folder: Path, run: dict[str, Any] | RunState) -> None:
    state = _coerce_run_state(run)
    payload = json.dumps(persist_run_meta(state), indent=2, ensure_ascii=False) + "\n"
    path = folder / "run.json"
    tmp = path.with_suffix(".json.tmp")
    with _folder_lock(folder):
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)


def patch_run_meta(
    folder: Path,
    updater: Callable[[RunState], dict[str, Any] | RunState],
) -> RunState:
    with _folder_lock(folder):
        run = read_run_meta(folder)
        capture_checkpoint = False
        prior_signature: tuple[str | None, str | None] = (None, None)
        if env_bool("AGENT_LAB_CHECKPOINT"):
            from agent_lab import checkpoint_store

            capture_checkpoint = True
            prior_signature = checkpoint_store._phase_signature(run)
        updated = updater(run)
        state = _coerce_run_state(updated)
        payload = json.dumps(persist_run_meta(state), indent=2, ensure_ascii=False) + "\n"
        path = folder / "run.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
        if capture_checkpoint:
            from agent_lab import checkpoint_store

            checkpoint_store.append_checkpoint(folder, prior_signature=prior_signature, updated_run=state)
    return state


def completed_step_key(*, human_turn: int, parallel_round: int, agent: str) -> str:
    return f"turn_{human_turn}_round_{parallel_round}_{agent.strip().lower()}"


def get_completed_step(
    run: RunStateLike,
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
    raw_steps = run.get("completed_steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    for step in steps:
        if isinstance(step, dict) and step.get("step") == key:
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
    run_meta: RunStateLike | None = None,
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
        "ts": utc_now_iso(),
        "content": content,
    }
    if envelope is not None:
        entry["envelope"] = envelope
    if msg_idx is not None:
        entry["msg_idx"] = msg_idx

    def _upsert(run: RunState) -> RunState:
        steps = [s for s in (run.get("completed_steps") or []) if s.get("step") != key]
        steps.append(entry)
        run["completed_steps"] = steps
        return run

    updated = patch_run_meta(folder, _upsert)
    if run_meta is not None:
        run_meta["completed_steps"] = updated.get("completed_steps")
    return updated


def clear_completed_steps_for_human_turn(folder: Path, human_turn: int) -> None:
    def _clear(run: RunState) -> RunState:
        steps = [s for s in (run.get("completed_steps") or []) if int(s.get("human_turn") or 0) != human_turn]
        run["completed_steps"] = steps
        return run

    patch_run_meta(folder, _clear)


def append_hook_run(
    folder: Path | None,
    record: dict[str, Any],
    *,
    run_meta: RunStateLike | None = None,
) -> None:
    """Append one hook run record to run.json (and optional in-memory run_meta)."""
    if folder is None:
        if run_meta is not None:
            runs = list(run_meta.get("hook_runs") or [])
            runs.append(record)
            run_meta["hook_runs"] = runs[-200:]
        return

    def _append(run: RunState) -> RunState:
        runs = list(run.get("hook_runs") or [])
        runs.append(record)
        run["hook_runs"] = runs[-200:]
        return run

    updated = patch_run_meta(folder, _append)
    if run_meta is not None:
        run_meta["hook_runs"] = updated.get("hook_runs")
