"""Typed event-envelope schema/validator (G6).

Pure stdlib, deterministic. Default OFF via AGENT_LAB_EVENT_MEMORY, and intentionally
NOT wired into any consumer this increment (zero consumer call sites => existing
event/log/SSE paths are byte-identical regardless of the flag).

``EVENT_TYPES`` is a canonical SUPERSET of ``room_live_log.LIVE_EVENT_TYPES`` (the
single source of truth, imported read-only) plus a small fixed set of already-emitted
SSE/runner types. This module does NOT modify or replace room_live_log; the existing
log may OPTIONALLY validate via ``validate_event`` in a later increment.

Directional import contract: this module imports ``room_live_log`` (one read-only
edge); ``room_live_log`` must never import this module back (that would let existing
log behavior change). Enforced by a test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent_lab.env_flags import env_bool
from agent_lab.room.live_log import LIVE_EVENT_TYPES

# Already-emitted-but-not-in-live-log event types (SSE/runner surfaces).
_EXTRA_EVENT_TYPES = frozenset({"node_status", "run_patch"})

# Canonical superset: every live-log type plus the extras. Single source of truth
# for the live-log portion guarantees the superset can never silently drift.
EVENT_TYPES: frozenset[str] = LIVE_EVENT_TYPES | _EXTRA_EVENT_TYPES


def event_memory_enabled() -> bool:
    """AGENT_LAB_EVENT_MEMORY (default ON): gates the memory route. Opt-out via =0."""
    return env_bool("AGENT_LAB_EVENT_MEMORY", default=True)


def event_validation_enabled() -> bool:
    """AGENT_LAB_EVENT_VALIDATE (default OFF): validate+drop invalid live-log events in Room turns."""
    return env_bool("AGENT_LAB_EVENT_VALIDATE")


def make_event(type: str, **fields: Any) -> dict[str, Any]:
    """Build a typed event envelope ``{ts, type, **fields}``.

    Stamps an ISO-8601 ``ts`` when not supplied in ``fields`` (an explicit ``ts``
    passes through unchanged, so a fixed ts makes the call reproducible). Raises
    ValueError if ``type`` is not in EVENT_TYPES. Pure.
    """
    if type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {type!r}")
    ts = fields.pop("ts", None) or datetime.now(timezone.utc).isoformat()
    return {"ts": ts, "type": type, **fields}


def validate_event(d: Any) -> tuple[bool, list[str]]:
    """Validate an event envelope; return ``(ok, errors)``.

    Errors (one per defect): "payload_not_dict" (not a dict), "unknown_type"
    (missing type or not in EVENT_TYPES), "missing_ts" (no/empty ts). ``ok`` is
    ``errors == []``. Pure/deterministic.
    """
    errors: list[str] = []
    if not isinstance(d, dict):
        return False, ["payload_not_dict"]
    typ = d.get("type")
    if not isinstance(typ, str) or typ not in EVENT_TYPES:
        errors.append("unknown_type")
    ts = d.get("ts")
    if not isinstance(ts, str) or not ts.strip():
        errors.append("missing_ts")
    return (errors == []), errors
