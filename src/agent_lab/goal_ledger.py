"""Goal-progress ledger embedded in run.json (AGENT_LAB_PIPELINE).

Optional, additive ``run.json["goal_ledger"]``: a capped list of ``{at, event, mode, phase, note}``
entries tracking pipeline goal progress. The field is leniently validated by run_schema and is
additive, so crash_recovery (which round-trips run.json through patch_run_meta/validate_run)
tolerates it without change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

GOAL_LEDGER_CAP = 200


def append_goal_event(
    folder: Any,
    event: str,
    *,
    mode: str | None = None,
    phase: str | None = None,
    note: str | None = None,
    dedup_mode: bool = False,
) -> dict[str, Any]:
    """Append a goal-progress entry to run.json goal_ledger (capped, optional dedup on mode)."""
    from agent_lab.run.meta import patch_run_meta

    entry: dict[str, Any] = {"at": datetime.now(timezone.utc).isoformat(), "event": event}
    if mode is not None:
        entry["mode"] = mode
    if phase is not None:
        entry["phase"] = phase
    if note is not None:
        entry["note"] = note

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
