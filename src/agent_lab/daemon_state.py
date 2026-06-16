"""Mission scheduler daemon state — ~/.agent-lab/daemon_state.json."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path.home() / ".agent-lab" / "daemon_state.json"


def daemon_state_path() -> Path:
    raw = (os.getenv("AGENT_LAB_DAEMON_STATE") or "").strip()
    return Path(raw).expanduser() if raw else _DEFAULT_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_daemon_state() -> dict[str, Any]:
    path = daemon_state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_daemon_state(state: dict[str, Any]) -> None:
    path = daemon_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def mark_daemon_started(*, pid: int) -> dict[str, Any]:
    state = load_daemon_state()
    state["pid"] = pid
    state["started_at"] = _now_iso()
    state["scheduler_enabled"] = True
    save_daemon_state(state)
    return state


def mark_scheduler_tick(result: dict[str, Any]) -> dict[str, Any]:
    state = load_daemon_state()
    state["last_scheduler_tick_at"] = _now_iso()
    state["last_scheduler_result"] = {
        "ok": result.get("ok"),
        "skipped": result.get("skipped"),
        "runs": len(result.get("runs") or []),
    }
    save_daemon_state(state)
    return state


def record_last_recovery(result: dict[str, Any]) -> dict[str, Any]:
    state = load_daemon_state()
    state["last_recovery_at"] = _now_iso()
    state["last_recovery_result"] = {
        key: result.get(key)
        for key in ("scanned", "reconciled_merged", "rolled_back", "quarantined", "errors")
    }
    save_daemon_state(state)
    return state


def public_daemon_payload() -> dict[str, Any]:
    state = load_daemon_state()
    return {
        "path": str(daemon_state_path()),
        "pid": state.get("pid"),
        "started_at": state.get("started_at"),
        "scheduler_enabled": bool(state.get("scheduler_enabled")),
        "last_scheduler_tick_at": state.get("last_scheduler_tick_at"),
        "last_scheduler_result": state.get("last_scheduler_result"),
        "last_recovery_at": state.get("last_recovery_at"),
        "last_recovery_result": state.get("last_recovery_result"),
    }
