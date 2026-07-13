"""Structured logging + in-memory counters for the dual-write bridge (``dual_write.py``).

Every ``mirror_*`` call result already carries ``enabled``/``mirrored``/``reason``/
``operation`` — this module classifies that result into a bucket, logs it, and
accumulates a live counter. Counters are in-memory only (reset on restart): the
durable trail is the log line itself (``agent-lab-api.log``, already configured
by ``app_logging.setup_app_logging``), not another JSON file written on every
route call.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent_lab.mission.dual_write")

_LOCK = threading.Lock()
_OPERATION_COUNTERS: dict[str, dict[str, int]] = {}
_DISABLED_TOTAL = 0

_BUCKETS = ("mirrored", "blocked_cohort", "expected_boundary", "error")

# Documented FSM boundaries — not cohort failures (see
# docs/redesign-2026-07/dual-write-cutover-scope-limitations-2026-07-13.md).
_EXPECTED_BOUNDARY_REASONS = frozenset({"mission_not_ready_to_execute"})


def _bucket(result: dict[str, Any]) -> str:
    if not result.get("enabled"):
        return "disabled"
    if result.get("mirrored"):
        return "mirrored"
    reason = str(result.get("reason") or "")
    if reason == "cohort_not_selected":
        return "blocked_cohort"
    if reason in _EXPECTED_BOUNDARY_REASONS:
        return "expected_boundary"
    return "error"


def record_dual_write_event(folder: Path, result: dict[str, Any]) -> dict[str, Any]:
    """Log + count one mirror_* outcome. Returns ``result`` unchanged (pass-through)."""
    global _DISABLED_TOTAL
    operation = str(result.get("operation") or "unknown")
    bucket = _bucket(result)
    with _LOCK:
        if bucket == "disabled":
            _DISABLED_TOTAL += 1
        else:
            row = _OPERATION_COUNTERS.setdefault(operation, dict.fromkeys(_BUCKETS, 0))
            row[bucket] = row.get(bucket, 0) + 1
    if bucket == "disabled":
        return result  # routine — the flag is simply off, not worth a log line every call
    message = "dual_write session=%s operation=%s bucket=%s mirrored=%s reason=%s state=%s"
    args = (folder.name, operation, bucket, result.get("mirrored"), result.get("reason") or "", result.get("state"))
    if bucket == "error":
        logger.warning(message, *args)
    else:
        # expected_boundary (e.g. mission_not_ready_to_execute) is documented cutover scope, not a failure.
        logger.info(message, *args)
    return result


def dual_write_counters_snapshot() -> dict[str, Any]:
    with _LOCK:
        return {
            "disabled_calls_total": _DISABLED_TOTAL,
            "operations": {op: dict(counts) for op, counts in _OPERATION_COUNTERS.items()},
        }


def reset_dual_write_counters() -> None:
    """Test-only — in-process counters are global state that must not leak across tests."""
    global _DISABLED_TOTAL
    with _LOCK:
        _OPERATION_COUNTERS.clear()
        _DISABLED_TOTAL = 0
