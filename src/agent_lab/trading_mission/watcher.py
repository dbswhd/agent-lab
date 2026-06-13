"""Trading Mission event watcher — freshness/overlay triggers (P2)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_lab.quant_utility_validation import detect_pipeline_root
from agent_lab.trading_mission.preflight import build_market_snapshot

_KST = timezone(timedelta(hours=9))
_DEFAULT_STATE = Path.home() / ".agent-lab" / "trading_mission_watcher_state.json"
_DEFAULT_QUEUE = Path.home() / ".agent-lab" / "trading_mission_queue.jsonl"


def watcher_state_path() -> Path:
    raw = (os.getenv("AGENT_LAB_TRADING_WATCHER_STATE") or "").strip()
    return Path(raw).expanduser() if raw else _DEFAULT_STATE


def watcher_queue_path() -> Path:
    raw = (os.getenv("AGENT_LAB_TRADING_MISSION_QUEUE") or "").strip()
    return Path(raw).expanduser() if raw else _DEFAULT_QUEUE


def _now_kst() -> datetime:
    return datetime.now(_KST)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _fingerprint(snapshot: dict[str, Any]) -> dict[str, Any]:
    overlay = snapshot.get("overlay_signals") or {}
    kr = overlay.get("kr_kospi_v1") if isinstance(overlay, dict) else {}
    freshness = snapshot.get("freshness") or {}
    return {
        "freshness_blocking": bool(freshness.get("blocking")),
        "action_flag": bool(isinstance(kr, dict) and kr.get("flag")),
        "kill_switch": bool(snapshot.get("kill_switch")),
        "trade_allowed": bool(snapshot.get("trade_allowed")),
    }


def _detect_events(
    prev: dict[str, Any],
    curr: dict[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if curr.get("action_flag") and not prev.get("action_flag"):
        events.append(
            {
                "kind": "delta",
                "trigger": "ACTION_REQUIRED.flag",
                "reason": "overlay action flag appeared",
            }
        )
    if curr.get("freshness_blocking") and not prev.get("freshness_blocking"):
        events.append(
            {
                "kind": "delta",
                "trigger": "freshness.blocking",
                "reason": "freshness became blocking",
            }
        )
    if curr.get("kill_switch") and not prev.get("kill_switch"):
        events.append(
            {
                "kind": "delta",
                "trigger": "kill_switch",
                "reason": "kill switch activated",
            }
        )
    return events


def _cooldown_seconds() -> int:
    raw = (os.getenv("AGENT_LAB_TRADING_WATCHER_COOLDOWN_SEC") or "1800").strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 1800


def _within_cooldown(state: dict[str, Any], trigger: str, now: datetime) -> bool:
    last_map = state.get("last_event_at") or {}
    if not isinstance(last_map, dict):
        return False
    raw = last_map.get(trigger)
    if not raw:
        return False
    try:
        last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=_KST)
    delta = now - last.astimezone(_KST)
    return delta.total_seconds() < _cooldown_seconds()


def enqueue_events(events: list[dict[str, Any]], *, queue_path: Path | None = None) -> int:
    if not events:
        return 0
    path = queue_path or watcher_queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as fh:
        for event in events:
            row = {
                **event,
                "enqueued_at": _now_kst().isoformat(),
                "status": "pending",
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    return written


def read_pending_queue(*, queue_path: Path | None = None, limit: int = 10) -> list[dict[str, Any]]:
    path = queue_path or watcher_queue_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("status", "pending") == "pending":
            rows.append(row)
    return rows[-limit:]


def mark_queue_done(trigger: str, *, queue_path: Path | None = None) -> None:
    path = queue_path or watcher_queue_path()
    if not path.is_file():
        return
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            lines.append(line)
            continue
        if (
            isinstance(row, dict)
            and row.get("status") == "pending"
            and row.get("trigger") == trigger
        ):
            row = dict(row)
            row["status"] = "done"
            row["done_at"] = _now_kst().isoformat()
            lines.append(json.dumps(row, ensure_ascii=False))
        else:
            lines.append(line)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def watcher_tick(
    pipeline: Path | None = None,
    *,
    enqueue: bool = True,
) -> dict[str, Any]:
    """Poll pipeline snapshot and emit delta mission events."""
    root = pipeline or detect_pipeline_root()
    if root is None:
        return {"ok": False, "reason": "pipeline root not found", "events": []}

    snapshot = build_market_snapshot(root)
    curr = _fingerprint(snapshot)
    state_path = watcher_state_path()
    state = _load_state(state_path)
    prev = state.get("last_fingerprint") if isinstance(state.get("last_fingerprint"), dict) else {}

    now = _now_kst()
    raw_events = _detect_events(prev, curr)
    events: list[dict[str, Any]] = []
    last_event_at = dict(state.get("last_event_at") or {})
    for event in raw_events:
        trigger = str(event.get("trigger") or "")
        if _within_cooldown(state, trigger, now):
            continue
        events.append(event)
        last_event_at[trigger] = now.isoformat()

    state["last_fingerprint"] = curr
    state["last_poll_at"] = now.isoformat()
    state["last_event_at"] = last_event_at
    _save_state(state_path, state)

    enqueued = enqueue_events(events) if enqueue and events else 0
    return {
        "ok": True,
        "pipeline": str(root),
        "fingerprint": curr,
        "events": events,
        "enqueued": enqueued,
    }
