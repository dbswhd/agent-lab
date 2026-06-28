"""S1 Phase A — outcome harvester: cross-session outcome ledger.

At turn end this module (a) patches ``turn_metrics`` into the just-written
``run.json`` turn and (b) appends one outcome line to ``.agent-lab/outcomes.jsonl``
under the project root. Both writes are independently flag-gated and fail-open:
any error is swallowed so the feedback machinery never blocks a room turn.

See docs/DESIGN-S1-FEEDBACK-LOOP.md (Phase A).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from weakref import WeakValueDictionary

from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.turn_metrics import build_turn_metrics
from agent_lab.wisdom.index import _tokenize

log = logging.getLogger(__name__)

OUTCOME_LEDGER_SCHEMA_VERSION = 1
_OUTCOMES_RELPATH = Path(".agent-lab") / "outcomes.jsonl"
_TRUE = frozenset({"1", "true", "yes", "on"})

_LOCK_GUARD = threading.Lock()
_PATH_LOCKS: WeakValueDictionary[str, threading.Lock] = WeakValueDictionary()


def _flag_on(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in _TRUE


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCK_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[key] = lock
        return lock


def outcomes_path(root: Path | None = None) -> Path:
    """Resolve ``.agent-lab/outcomes.jsonl`` under the project root.

    Resolution order: explicit ``root`` arg → ``AGENT_LAB_OUTCOMES_ROOT`` env
    (S1.5 dogfood isolation) → workspace project root.
    """
    if root is None:
        env_root = (os.getenv("AGENT_LAB_OUTCOMES_ROOT") or "").strip()
        if env_root:
            root = Path(env_root)
        else:
            from agent_lab.workspace.roots import project_root

            root = project_root()
    return root / _OUTCOMES_RELPATH


def _topic_text(folder: Path, run: dict[str, Any]) -> str:
    topic = str(run.get("topic") or "").strip()
    if topic:
        return topic
    topic_file = folder / "topic.txt"
    if topic_file.is_file():
        try:
            return topic_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def _topic_hash(topic: str) -> str:
    return "sha1:" + hashlib.sha1(topic.encode("utf-8")).hexdigest()[:16]


def build_outcome_record(folder: Path, topic: str, metrics: dict[str, Any]) -> dict[str, Any]:
    """Flatten turn_metrics into one cross-session ledger row."""
    rollup = metrics.get("oracle_rollup") or {}
    return {
        "v": OUTCOME_LEDGER_SCHEMA_VERSION,
        "ts": _now_iso(),
        "session_id": folder.name,
        "topic_hash": _topic_hash(topic),
        "topic_terms": sorted(_tokenize(topic))[:24],
        "category": metrics.get("category") or "",
        "roles": metrics.get("roles") or {},
        "agents": metrics.get("agents") or [],
        "rounds_used": metrics.get("rounds_used") or 0,
        "escalated": bool(metrics.get("escalated")),
        "final_verdict": rollup.get("final_verdict"),
        "repair_attempts": rollup.get("repair_attempts") or 0,
        "objection_summary": metrics.get("objection_summary") or {},
        "consensus_reached": bool(metrics.get("consensus_reached")),
        "latency_ms": metrics.get("latency_ms") or 0,
        # S1.5 — advisor attribution (absent/"default" = baseline bucket in reports)
        "advisor_source": metrics.get("advisor_source") or "default",
        "combo_id": metrics.get("advisor_combo_id") or "",
    }


def append_outcome(record: dict[str, Any], *, root: Path | None = None) -> None:
    """Atomically append one JSON line to the outcomes ledger."""
    path = outcomes_path(root)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _path_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)


def record_turn_outcome(folder: Path | None, human_turn: int) -> None:
    """Persist turn_metrics + append to the outcome ledger (flag-gated, fail-open).

    Called from ``_finalize_durable_turn`` after run.json has been written for a
    completed turn. ``AGENT_LAB_TURN_METRICS`` gates the run.json patch;
    ``AGENT_LAB_OUTCOME_LEDGER`` gates the ledger append.
    """
    if folder is None:
        return
    want_metrics = _flag_on("AGENT_LAB_TURN_METRICS")
    want_ledger = _flag_on("AGENT_LAB_OUTCOME_LEDGER")
    if not (want_metrics or want_ledger):
        return
    try:
        run = read_run_meta(folder)
        turns = run.get("turns") or []
        if not turns:
            return
        metrics = build_turn_metrics(
            turns[-1],
            objections=run.get("objections") or [],
            executions=run.get("executions") or [],
            human_turn=human_turn,
        )
        if want_metrics:

            def _patch(current: dict[str, Any]) -> dict[str, Any]:
                rows = current.get("turns")
                if isinstance(rows, list) and rows and isinstance(rows[-1], dict):
                    rows[-1]["turn_metrics"] = metrics
                return current

            patch_run_meta(folder, _patch)
        if want_ledger:
            append_outcome(build_outcome_record(folder, _topic_text(folder, run), metrics))
    except Exception:  # fail-open: feedback must never block a turn
        log.warning("record_turn_outcome failed for %s", folder, exc_info=True)
