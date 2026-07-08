"""HS1 MINE — per-turn traces + recurring weakness-pattern mining.

Flag-gated (``AGENT_LAB_WEAKNESS_MINER``, default off). Fail-open like the S1
harvesters it sits beside (``outcome_harvester.py``): any error is swallowed so
this machinery never blocks a room turn.

Three pieces, matching docs/DESIGN-HARNESS-SELF-IMPROVE.md §9 HS1:
- HS1-3 ``write_turn_trace``: durable per-turn snapshot at
  ``.agent-lab/traces/{session}/{turn}/summary.json``.
- HS1-4 ``_preserve_failure_memory``: first ``memory_store`` consumer — turns
  that surfaced a failure tag are kept under namespace ``failures/{session_id}``
  even if a later turn resolves them (negative-result preservation narrows the
  search space for HS3 PROPOSE — see Weng #3 in the design doc).
- HS1-2/HS1-5 ``mine_weakness_patterns``: pure read/aggregate over the outcome
  ledger (same shape as ``feedback_report.build_feedback_report`` — no ledger
  mutation), grouping by ``pattern_id = fp:{primary_tag}:{category}`` and
  flagging ``addressable`` once a pattern recurs across >= MIN_PATTERN_SAMPLE
  distinct sessions.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any
from weakref import WeakValueDictionary

from agent_lab.env_flags import env_bool

log = logging.getLogger(__name__)

MIN_PATTERN_SAMPLE = 3
TRACE_SCHEMA_VERSION = 1

_LOCK_GUARD = threading.Lock()
_PATH_LOCKS: WeakValueDictionary[str, threading.Lock] = WeakValueDictionary()


def _path_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCK_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[key] = lock
        return lock


def weakness_miner_enabled() -> bool:
    """AGENT_LAB_WEAKNESS_MINER (default off)."""
    return env_bool("AGENT_LAB_WEAKNESS_MINER")


def traces_root(root: Path | None = None) -> Path:
    from agent_lab.outcome_harvester import agent_lab_project_root

    return agent_lab_project_root(root) / ".agent-lab" / "traces"


def trace_path(session_id: str, human_turn: int, *, root: Path | None = None) -> Path:
    return traces_root(root) / session_id / str(human_turn) / "summary.json"


def _memory_path(root: Path | None = None) -> Path:
    from agent_lab.outcome_harvester import agent_lab_project_root

    return agent_lab_project_root(root) / ".agent-lab" / "memory" / "failures.jsonl"


def _preserve_failure_memory(session_id: str, trace: dict[str, Any], *, root: Path | None = None) -> None:
    """HS1-4 — first memory_store consumer (see module docstring)."""
    from agent_lab.memory_store import MemoryStore

    path = _memory_path(root)
    with _path_lock(path):
        store = MemoryStore()
        if path.is_file():
            store.load(path)
        turn_metrics = trace.get("turn_metrics") or {}
        key = f"turn{trace.get('human_turn')}:{turn_metrics.get('primary_tag')}"
        store.put(f"failures/{session_id}", key, trace)
        store.dump(path)


def write_turn_trace(folder: Path | None, human_turn: int, *, root: Path | None = None) -> dict[str, Any] | None:
    """HS1-3 — write ``.agent-lab/traces/{session}/{turn}/summary.json``.

    Independently rebuilds ``turn_metrics`` (rather than reading run.json's
    S1-flag-gated copy) so HS1 works standalone regardless of
    ``AGENT_LAB_TURN_METRICS`` state. When the trace carries a failure tag,
    also preserves it via HS1-4 memory_store. No-op (returns ``None``) when
    the flag is off or there is no turn to trace; never raises.
    """
    if folder is None or not weakness_miner_enabled():
        return None
    try:
        from agent_lab.run.meta import read_run_meta
        from agent_lab.turn_metrics import build_turn_metrics

        run = read_run_meta(folder)
        turns = run.get("turns") or []
        if not turns or not isinstance(turns[-1], dict):
            return None
        metrics = build_turn_metrics(
            turns[-1],
            objections=run.get("objections") or [],
            executions=run.get("executions") or [],
            human_turn=human_turn,
        )
        trace = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "session_id": folder.name,
            "human_turn": human_turn,
            "turn_metrics": metrics,
        }
        path = trace_path(folder.name, human_turn, root=root)
        with _path_lock(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if metrics.get("failure_tags"):
            _preserve_failure_memory(folder.name, trace, root=root)
        return trace
    except Exception:  # fail-open: HS1 must never block a turn
        log.warning("write_turn_trace failed for %s", folder, exc_info=True)
        return None


def mine_weakness_patterns(root: Path | None = None) -> dict[str, Any]:
    """HS1-2/HS1-5 — group tagged outcome-ledger rows into recurring patterns.

    Pure read/aggregate, no ledger mutation (mirrors
    ``feedback_report.build_feedback_report``). ``pattern_id`` is
    ``fp:{primary_tag}:{category}`` (category is the coarsest generally-available
    discriminator; finer sub-labels need instrumentation this increment doesn't
    add). ``recurrence_count`` counts distinct sessions, not raw rows, so one
    chatty session can't fake a recurring pattern on its own.
    """
    from agent_lab.outcome_harvester import load_outcome_rows

    rows = load_outcome_rows(root)
    by_pattern: dict[str, dict[str, Any]] = {}
    for row in rows:
        primary_tag = row.get("primary_tag")
        if not primary_tag:
            continue
        category = str(row.get("category") or "unknown")
        pattern_id = f"fp:{primary_tag}:{category}"
        bucket = by_pattern.setdefault(
            pattern_id,
            {"pattern_id": pattern_id, "primary_tag": str(primary_tag), "category": category, "session_ids": set()},
        )
        session_id = str(row.get("session_id") or "")
        if session_id:
            bucket["session_ids"].add(session_id)

    patterns = []
    for bucket in by_pattern.values():
        recurrence_count = len(bucket["session_ids"])
        patterns.append(
            {
                "pattern_id": bucket["pattern_id"],
                "primary_tag": bucket["primary_tag"],
                "category": bucket["category"],
                "recurrence_count": recurrence_count,
                "addressable": recurrence_count >= MIN_PATTERN_SAMPLE,
            }
        )
    patterns.sort(key=lambda p: (-p["recurrence_count"], p["pattern_id"]))
    return {"patterns": patterns, "min_pattern_sample": MIN_PATTERN_SAMPLE}
