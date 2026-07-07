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
from agent_lab.run.state import RunStateLike
from agent_lab.s1_flags import s1_flag_enabled
from agent_lab.turn_metrics import build_turn_metrics
from agent_lab.wisdom.index import _tokenize

log = logging.getLogger(__name__)

OUTCOME_LEDGER_SCHEMA_VERSION = 1
_OUTCOMES_RELPATH = Path(".agent-lab") / "outcomes.jsonl"

_LOCK_GUARD = threading.Lock()
_PATH_LOCKS: WeakValueDictionary[str, threading.Lock] = WeakValueDictionary()


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


def _default_outcomes_root() -> Path:
    """Repo root for the outcomes ledger (not ``src/`` package root).

    ``project_root()`` resolves to ``…/src`` for the in-tree package layout.
    Outcomes are written under the git/repo root ``.agent-lab/outcomes.jsonl``.
    """
    env_root = (os.getenv("AGENT_LAB_OUTCOMES_ROOT") or "").strip()
    if env_root:
        return Path(env_root)
    from agent_lab.workspace.roots import project_root

    root = project_root()
    # In-tree layout: src/agent_lab/… → project_root is …/src; ledger lives on parent.
    if root.name == "src" and (root.parent / ".agent-lab").is_dir():
        return root.parent
    if root.name == "src" and (root.parent / "pyproject.toml").is_file():
        return root.parent
    return root


def outcomes_path(root: Path | None = None) -> Path:
    """Resolve ``.agent-lab/outcomes.jsonl`` under the project root.

    Resolution order: explicit ``root`` arg → ``AGENT_LAB_OUTCOMES_ROOT`` env
    (S1.5 dogfood isolation) → repo root (not ``src/``).
    """
    if root is None:
        root = _default_outcomes_root()
    return Path(root) / _OUTCOMES_RELPATH


def _topic_text(folder: Path, run: RunStateLike) -> str:
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


def build_outcome_record(
    folder: Path, topic: str, metrics: dict[str, Any], *, run_meta: RunStateLike | None = None
) -> dict[str, Any]:
    """Flatten turn_metrics into one cross-session ledger row."""
    from agent_lab.autonomy_ladder import infer_effective_autonomy_level
    from agent_lab.human_inbox import pending_inbox_items

    rollup = metrics.get("oracle_rollup") or {}
    run = run_meta or {}
    level = infer_effective_autonomy_level(run)
    inbox_hit = bool(metrics.get("escalated")) or bool(pending_inbox_items(run))
    return {
        "v": OUTCOME_LEDGER_SCHEMA_VERSION,
        "ts": _now_iso(),
        # "turn" (Room turn close) vs "execute" (see record_execute_outcome).
        # Absent on rows written before this field existed — readers treat
        # missing phase as "turn" for backward compatibility.
        "phase": "turn",
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
        "objection_resolution": metrics.get("objection_resolution") or {},
        "consensus_reached": bool(metrics.get("consensus_reached")),
        "latency_ms": metrics.get("latency_ms") or 0,
        # S1.5 — advisor attribution (absent/"default" = baseline bucket in reports)
        "advisor_source": metrics.get("advisor_source") or "default",
        "combo_id": metrics.get("advisor_combo_id") or "",
        "autonomy_level": level,
        "human_inbox_escalation": inbox_hit,
        # S3a-0 — tool cards suggested at RECALL time (installed-but-unused capabilities)
        "tool_card_suggestions": list(metrics.get("tool_card_suggestions") or []),
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
    try:
        run = read_run_meta(folder)
        want_metrics = s1_flag_enabled("AGENT_LAB_TURN_METRICS", run_meta=run)
        want_ledger = s1_flag_enabled("AGENT_LAB_OUTCOME_LEDGER", run_meta=run)
        if not (want_metrics or want_ledger):
            return
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

            def _patch(current: RunStateLike) -> RunStateLike:
                rows = current.get("turns")
                if isinstance(rows, list) and rows and isinstance(rows[-1], dict):
                    rows[-1]["turn_metrics"] = metrics
                return current

            patch_run_meta(folder, _patch)
        if want_ledger:
            append_outcome(build_outcome_record(folder, _topic_text(folder, run), metrics, run_meta=run))
    except Exception:  # fail-open: feedback must never block a turn
        log.warning("record_turn_outcome failed for %s", folder, exc_info=True)


def record_execute_outcome(folder: Path | None, execution: dict[str, Any]) -> None:
    """Persist one execute-completion outcome row (flag-gated, fail-open).

    ``record_turn_outcome`` only fires when a Room turn closes, and rolls up
    whatever ``executions`` exist in run.json *at that moment*. Oracle
    verdicts are decided by execute/verify, which normally happens *after*
    the turn that produced the plan has already closed its ledger row — so a
    session with no follow-up chat turn after execute never emits a row
    carrying the verdict, and the S1 lift signal (§1.4 KPI) stays permanently
    empty (2026-07 diagnosis: 40/40 ledger rows had ``final_verdict: null``).

    Called from ``_record_verify_after_merge`` right after one execution's
    Oracle verdict is known, so it also fires once per repair-retry attempt.
    Reuses the last Room turn's category/roles/agents for the S2 episode key
    (mission x agent-subset x result, §1 S2) since execute itself has no
    role-combo concept of its own.
    """
    if folder is None:
        return
    try:
        run = read_run_meta(folder)
        if not s1_flag_enabled("AGENT_LAB_OUTCOME_LEDGER", run_meta=run):
            return
        turns = run.get("turns") or []
        last_turn = turns[-1] if turns and isinstance(turns[-1], dict) else {}
        category = last_turn.get("category") if isinstance(last_turn.get("category"), dict) else {}
        roles = last_turn.get("roles") if isinstance(last_turn.get("roles"), dict) else {}
        consensus = last_turn.get("consensus") if isinstance(last_turn.get("consensus"), dict) else {}

        oracle = execution.get("oracle") if isinstance(execution.get("oracle"), dict) else {}
        verdict = str(oracle.get("verdict") or "").strip().lower()
        if not verdict:
            status = str((execution.get("verify_after_merge") or {}).get("status") or "").strip().lower()
            verdict = {"passed": "pass", "failed": "fail"}.get(status, "")

        topic = _topic_text(folder, run)
        record = {
            "v": OUTCOME_LEDGER_SCHEMA_VERSION,
            "ts": _now_iso(),
            "phase": "execute",
            "session_id": folder.name,
            "topic_hash": _topic_hash(topic),
            "topic_terms": sorted(_tokenize(topic))[:24],
            "category": str(category.get("value") or ""),
            "roles": {str(k): str(v) for k, v in roles.items()},
            "agents": list(last_turn.get("agents") or []),
            "rounds_used": int(last_turn.get("agent_parallel_rounds") or 0),
            "escalated": bool(category.get("escalated_from")),
            "execution_id": str(execution.get("id") or ""),
            "final_verdict": verdict or None,
            "repair_attempts": len(execution.get("repair_history") or []),
            "objection_summary": {},
            "objection_resolution": {},
            "consensus_reached": str(consensus.get("status") or "") == "reached",
            "latency_ms": 0,
            "advisor_source": category.get("advisor_source") or "default",
            "combo_id": category.get("advisor_combo_id") or "",
            "tool_card_suggestions": list(category.get("tool_card_suggestions") or []),
        }
        from agent_lab.autonomy_ladder import infer_effective_autonomy_level
        from agent_lab.human_inbox import pending_inbox_items

        record["autonomy_level"] = infer_effective_autonomy_level(run)
        record["human_inbox_escalation"] = bool(pending_inbox_items(run))

        # N6 — self-patch eligibility classification (audit-only; no gate change,
        # see self_patch.py). Never affects whether Human approval was required.
        from agent_lab.self_patch import classify_self_patch

        touched = list(execution.get("source_touched_paths") or execution.get("touched_paths") or [])
        record["self_patch"] = classify_self_patch(touched)
        append_outcome(record)
    except Exception:  # fail-open: feedback must never block execute
        log.warning("record_execute_outcome failed for %s", folder, exc_info=True)
