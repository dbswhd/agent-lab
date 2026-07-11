"""Per-phase FSM checkpoint store for run.json (AGENT_LAB_CHECKPOINT).

Optional, additive, default-off. When ``AGENT_LAB_CHECKPOINT`` is enabled, the single
``run_meta.patch_run_meta`` chokepoint appends a snapshot of the run.json FSM subset to a
per-session append-only ``sessions/<id>/checkpoints.jsonl`` whenever a phase transition is
detected (prior phase signature != next). An operator can later restore a chosen snapshot
into run.json via :func:`resume_from_checkpoint`, which restores-then-stops (no FSM tick or
re-execution).

Design invariants:
- Pure stdlib only; no cross-lane imports (run_meta lazy-imports this module inside its flag
  guard, so this module must not import room/mission/plan_execute lanes).
- Snapshot scope is strictly the FSM subset (:data:`CHECKPOINT_FSM_KEYS`) — never chat.jsonl,
  plan.md, or artifacts.
- Restore writes via ``write_run_meta`` (which validates) and therefore bypasses the capture
  hook in ``patch_run_meta`` — a restore is a deliberate rewind, never recorded as a new
  checkpoint.
- ``crash_recovery`` (in-flight worktree merge reconcile) is independent and untouched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_lab.time_utils import utc_now_iso as _now_iso
from agent_lab.run.state import RunStateLike

CHECKPOINTS_FILE = "checkpoints.jsonl"
CHECKPOINT_CAP = 200
_TRUE = frozenset({"1", "true", "yes", "on"})

# The run.json FSM/ledger/budget subset captured and restored by a checkpoint. The SAME
# constant drives both snapshot and restore so capture and restore can never drift.
CHECKPOINT_FSM_KEYS: tuple[str, ...] = (
    "mission_loop",
    "plan_workflow",
    "verified_loop",
    "goal_ledger",
    "token_budget",
    "cost_ledger",
    "budget_status",
    "budget_exhausted",
)


def checkpoint_enabled() -> bool:
    """AGENT_LAB_CHECKPOINT (default ON): per-phase FSM snapshot + manual resume. Opt-out via =0."""
    raw = os.getenv("AGENT_LAB_CHECKPOINT")
    if raw is None or raw.strip() == "":
        return True
    return raw.strip().lower() in _TRUE


def _fsm_subset(run: RunStateLike) -> dict[str, Any]:
    """Extract the FSM/ledger/budget subset present in ``run`` (deep-copied via json)."""
    subset: dict[str, Any] = {}
    for key in CHECKPOINT_FSM_KEYS:
        if key in run:
            subset[key] = json.loads(json.dumps(run[key]))
    return subset


def _phase_signature(run: RunStateLike | None) -> tuple[str | None, str | None]:
    """(mission_loop.phase, plan_workflow.phase) for transition detection."""
    if not isinstance(run, dict):
        return (None, None)
    ml = run.get("mission_loop")
    pw = run.get("plan_workflow")
    mission_phase = ml.get("phase") if isinstance(ml, dict) else None
    plan_phase = pw.get("phase") if isinstance(pw, dict) else None
    return (
        str(mission_phase) if mission_phase is not None else None,
        str(plan_phase) if plan_phase is not None else None,
    )


def _checkpoints_path(folder: Path) -> Path:
    return folder / CHECKPOINTS_FILE


def _read_checkpoints(folder: Path) -> list[dict[str, Any]]:
    path = _checkpoints_path(folder)
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            records.append(entry)
    return records


def append_checkpoint(
    folder: Path,
    *,
    prior_signature: tuple[str | None, str | None],
    updated_run: dict[str, Any],
) -> dict[str, Any] | None:
    """Append one FSM snapshot to checkpoints.jsonl iff the phase signature changed.

    Returns the appended record, or ``None`` when there was no phase transition. Caller is
    responsible for the flag guard; this only no-ops on an unchanged signature.
    """
    next_signature = _phase_signature(updated_run)
    if prior_signature == next_signature:
        return None

    records = _read_checkpoints(folder)
    session_id = str(updated_run.get("_session_id") or folder.name)
    record: dict[str, Any] = {
        "n": (records[-1].get("n", len(records) - 1) + 1) if records else 0,
        "session_id": session_id,
        "prior_phase": list(prior_signature),
        "next_phase": list(next_signature),
        "fsm_state": _fsm_subset(updated_run),
        "at": _now_iso(),
    }
    records.append(record)
    if len(records) > CHECKPOINT_CAP:
        records = records[-CHECKPOINT_CAP:]

    path = _checkpoints_path(folder)
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    return record


def list_checkpoints(folder: Path) -> list[dict[str, Any]]:
    """Read-only view of stored checkpoints (oldest first)."""
    return _read_checkpoints(folder)


def resume_from_checkpoint(folder: Path, n: int) -> dict[str, Any]:
    """Restore the FSM subset from checkpoint ``n`` into run.json, then stop.

    Restores via ``write_run_meta`` (which validates) so the capture hook in ``patch_run_meta``
    is bypassed and the restore is NOT recorded as a new checkpoint. Performs no FSM tick,
    dispatch, or re-execution — the operator reviews and advances manually. Raises
    ``KeyError`` when no checkpoint matches ``n``.
    """
    from agent_lab.run.meta import read_run_meta, write_run_meta

    records = _read_checkpoints(folder)
    match = next((r for r in records if r.get("n") == n), None)
    if match is None:
        raise KeyError(f"checkpoint n={n} not found in {_checkpoints_path(folder)}")

    fsm_state = match.get("fsm_state")
    if not isinstance(fsm_state, dict):
        raise KeyError(f"checkpoint n={n} has no fsm_state")

    run = read_run_meta(folder)
    for key in CHECKPOINT_FSM_KEYS:
        if key in fsm_state:
            run[key] = json.loads(json.dumps(fsm_state[key]))
    write_run_meta(folder, run)
    return run
