"""Decision latency KPI (Phase B1) — Human gate wait times.

Records open→close waits for Decision Queue blocking states into ``run.json``
under ``decision_latency``. Does not weaken gates; observational only.
"""

from __future__ import annotations

from typing import Any

from agent_lab.time_utils import utc_now_iso_z
from agent_lab.run.state import RunStateLike

_MAX_EVENTS = 50


def _parse_iso_ts(raw: str) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        from datetime import datetime

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def _bucket(run: dict[str, Any]) -> dict[str, Any]:
    raw = run.get("decision_latency")
    if isinstance(raw, dict):
        return raw
    out: dict[str, Any] = {"open": None, "events": []}
    run["decision_latency"] = out
    return out


def record_gate_opened(run: RunStateLike | None, *, kind: str) -> bool:
    """Stamp Human-gate open if none is active. Returns True when stamped."""
    if not isinstance(run, dict):
        return False
    kind_s = (kind or "").strip() or "unknown"
    bucket = _bucket(run)
    open_row = bucket.get("open")
    if isinstance(open_row, dict) and open_row.get("opened_at"):
        # Keep earliest open for the same kind; switch kind only if previously closed.
        if str(open_row.get("kind") or "") == kind_s:
            return False
        return False
    bucket["open"] = {
        "kind": kind_s,
        "opened_at": utc_now_iso_z(),
    }
    return True


def record_gate_closed(
    run: RunStateLike | None,
    *,
    kind: str | None = None,
    action: str = "resolved",
) -> dict[str, Any] | None:
    """Close active gate and append an event with wait_ms. Returns the event or None."""
    if not isinstance(run, dict):
        return None
    bucket = _bucket(run)
    open_row = bucket.get("open")
    if not isinstance(open_row, dict):
        return None
    opened_at = str(open_row.get("opened_at") or "")
    opened_kind = str(open_row.get("kind") or "unknown")
    if kind and kind.strip() and kind.strip() != opened_kind:
        # Closing a different gate — still close the active one.
        pass
    closed_at = utc_now_iso_z()
    opened_ts = _parse_iso_ts(opened_at)
    closed_ts = _parse_iso_ts(closed_at)
    wait_ms: int | None = None
    if opened_ts is not None and closed_ts is not None and closed_ts >= opened_ts:
        wait_ms = int(round((closed_ts - opened_ts) * 1000))
    event = {
        "kind": opened_kind,
        "action": (action or "resolved").strip() or "resolved",
        "opened_at": opened_at,
        "closed_at": closed_at,
        "wait_ms": wait_ms,
    }
    events = bucket.get("events")
    if not isinstance(events, list):
        events = []
        bucket["events"] = events
    events.append(event)
    if len(events) > _MAX_EVENTS:
        del events[: len(events) - _MAX_EVENTS]
    bucket["open"] = None
    return event


def active_gate(run: RunStateLike | None) -> dict[str, Any] | None:
    if not isinstance(run, dict):
        return None
    raw = run.get("decision_latency")
    if not isinstance(raw, dict):
        return None
    open_row = raw.get("open")
    return open_row if isinstance(open_row, dict) and open_row.get("opened_at") else None


def summarize_decision_latency(run: RunStateLike | None) -> dict[str, Any]:
    """Return count / p50 / p95 wait seconds from recorded events."""
    empty = {
        "count": 0,
        "p50_sec": None,
        "p95_sec": None,
        "open": active_gate(run),
    }
    if not isinstance(run, dict):
        return empty
    raw = run.get("decision_latency")
    if not isinstance(raw, dict):
        return empty
    events = raw.get("events")
    if not isinstance(events, list):
        return empty
    waits: list[float] = []
    for row in events:
        if not isinstance(row, dict):
            continue
        wait_ms = row.get("wait_ms")
        if isinstance(wait_ms, (int, float)) and wait_ms >= 0:
            waits.append(float(wait_ms) / 1000.0)
    if not waits:
        return empty
    waits.sort()

    def _pct(p: float) -> float:
        if len(waits) == 1:
            return round(waits[0], 3)
        idx = min(len(waits) - 1, max(0, int(round((p / 100.0) * (len(waits) - 1)))))
        return round(waits[idx], 3)

    return {
        "count": len(waits),
        "p50_sec": _pct(50),
        "p95_sec": _pct(95),
        "open": active_gate(run),
    }
