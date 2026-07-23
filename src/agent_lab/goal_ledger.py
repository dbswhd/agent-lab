"""Goal-progress ledger embedded in run.json (AGENT_LAB_PIPELINE).

Optional, additive ``run.json["goal_ledger"]``: a capped list of
``{at, event, mode, phase, note, payload}`` entries tracking pipeline goal progress. ``payload``
is an optional structured sub-dict for policy-decision events (e.g. mission_topology's
decision/revision/trigger) — ``note`` stays the human-readable rendering that existing consumers
(context/bundle.py, context/adapters.py) already parse, so adding ``payload`` is additive and
backward compatible. The field is leniently validated by run_schema and is additive, so
crash_recovery (which round-trips run.json through patch_run_meta/validate_run) tolerates it
without change.
"""

from __future__ import annotations

from typing import Any

from agent_lab.time_utils import utc_now_iso

GOAL_LEDGER_CAP = 200


def append_goal_event(
    folder: Any,
    event: str,
    *,
    mode: str | None = None,
    phase: str | None = None,
    note: str | None = None,
    payload: dict[str, Any] | None = None,
    dedup_mode: bool = False,
) -> dict[str, Any]:
    """Append a goal-progress entry to run.json goal_ledger (capped, optional dedup on mode)."""
    from agent_lab.run.meta import patch_run_meta

    entry: dict[str, Any] = {"at": utc_now_iso(), "event": event}
    if mode is not None:
        entry["mode"] = mode
    if phase is not None:
        entry["phase"] = phase
    if note is not None:
        entry["note"] = note
    if payload is not None:
        entry["payload"] = payload

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        raw = run.get("goal_ledger")
        ledger = list(raw) if isinstance(raw, list) else []
        if (
            dedup_mode
            and ledger
            and isinstance(ledger[-1], dict)
            and ledger[-1].get("mode") == mode
            and ledger[-1].get("event") == event
        ):
            return run
        ledger.append(entry)
        if len(ledger) > GOAL_LEDGER_CAP:
            ledger = ledger[-GOAL_LEDGER_CAP:]
        run["goal_ledger"] = ledger
        return run

    patch_run_meta(folder, _patch)
    return entry
