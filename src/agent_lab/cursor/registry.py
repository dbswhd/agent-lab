"""Cursor SDK bridge process registry — stale bridge audit and cleanup (M4)."""

from __future__ import annotations

from agent_lab.time_utils import utc_now_iso as _now_iso
import json
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_REGISTRY_FILE = "bridge_registry.json"
_BRIDGE_NAME_MARKERS = ("cursor-sdk-bridge", "cursor_sdk_bridge")



def registry_path() -> Path:
    from agent_lab.app_config import config_dir

    return config_dir() / _REGISTRY_FILE


@dataclass
class BridgeRecord:
    workspace: str
    mode: str = "auto"
    pid: int | None = None
    bridge_url: str | None = None
    registered_at: str = field(default_factory=_now_iso)
    last_seen_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _abs_workspace(workspace: str) -> str:
    return os.path.abspath(os.path.expanduser(workspace))


def load_records() -> list[BridgeRecord]:
    path = registry_path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = raw.get("records") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return []
    out: list[BridgeRecord] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("workspace"):
            continue
        fields = {k: row[k] for k in BridgeRecord.__dataclass_fields__ if k in row}
        out.append(BridgeRecord(**fields))
    return out


def save_records(records: list[BridgeRecord]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _now_iso(),
        "records": [r.to_dict() for r in records],
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def register_bridge(
    workspace: str,
    *,
    pid: int | None = None,
    mode: str = "auto",
    bridge_url: str | None = None,
) -> BridgeRecord:
    ws = _abs_workspace(workspace)
    now = _now_iso()
    records = load_records()
    kept = [r for r in records if r.workspace != ws]
    record = BridgeRecord(
        workspace=ws,
        mode=mode,
        pid=pid,
        bridge_url=bridge_url,
        registered_at=now,
        last_seen_at=now,
    )
    kept.append(record)
    save_records(kept)
    return record


def touch_bridge(workspace: str, *, pid: int | None = None) -> None:
    ws = _abs_workspace(workspace)
    records = load_records()
    touched = False
    for record in records:
        if record.workspace == ws:
            record.last_seen_at = _now_iso()
            if pid is not None:
                record.pid = pid
            touched = True
            break
    if not touched:
        records.append(
            BridgeRecord(workspace=ws, pid=pid, last_seen_at=_now_iso()),
        )
    save_records(records)


def remove_workspace(workspace: str) -> bool:
    ws = _abs_workspace(workspace)
    records = load_records()
    kept = [r for r in records if r.workspace != ws]
    if len(kept) == len(records):
        return False
    save_records(kept)
    return True


def _pid_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def list_live_bridge_processes() -> list[dict[str, Any]]:
    """Best-effort scan of cursor-sdk-bridge processes on this host."""
    try:
        proc = subprocess.run(
            ["pgrep", "-fl", "cursor-sdk-bridge"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows: list[dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        cmd = parts[1] if len(parts) > 1 else ""
        if not any(marker in cmd for marker in _BRIDGE_NAME_MARKERS):
            continue
        rows.append({"pid": pid, "command": cmd, "alive": _pid_alive(pid)})
    return rows


def guess_bridge_pid(*, settle_s: float = 0.15) -> int | None:
    """Return the newest bridge PID after a short settle window."""
    if settle_s > 0:
        from agent_lab.backoff_policy import wait as _backoff_wait

        _backoff_wait(1, base_sec=settle_s)
    live = list_live_bridge_processes()
    if not live:
        return None
    return max(int(row["pid"]) for row in live if row.get("pid"))


def audit_bridge_processes(
    *,
    stale_after_hours: float = 24.0,
) -> dict[str, Any]:
    records = load_records()
    live = list_live_bridge_processes()
    live_pids = {int(row["pid"]) for row in live if row.get("pid")}
    now = time.time()
    stale_after_s = stale_after_hours * 3600.0

    stale_records: list[dict[str, Any]] = []
    active_records: list[dict[str, Any]] = []
    for record in records:
        row = record.to_dict()
        pid_alive = _pid_alive(record.pid)
        try:
            seen_ts = datetime.fromisoformat(record.last_seen_at).timestamp()
        except ValueError:
            seen_ts = 0.0
        age_s = max(0.0, now - seen_ts)
        row["pid_alive"] = pid_alive
        row["age_hours"] = round(age_s / 3600.0, 2)
        is_stale = (record.pid is not None and not pid_alive) or (age_s > stale_after_s and record.pid not in live_pids)
        row["stale"] = is_stale
        if is_stale:
            stale_records.append(row)
        else:
            active_records.append(row)

    orphan_pids = [row for row in live if int(row["pid"]) not in {r.pid for r in records if r.pid is not None}]

    return {
        "registry_path": str(registry_path()),
        "record_count": len(records),
        "active_count": len(active_records),
        "stale_count": len(stale_records),
        "orphan_process_count": len(orphan_pids),
        "records": records and [r.to_dict() for r in records],
        "active_records": active_records,
        "stale_records": stale_records,
        "live_processes": live,
        "orphan_processes": orphan_pids,
    }


def cleanup_stale_bridges(
    *,
    kill_orphans: bool = False,
    prune_registry: bool = True,
) -> dict[str, Any]:
    audit = audit_bridge_processes()
    removed_registry = 0
    killed: list[int] = []

    if prune_registry:
        kept: list[BridgeRecord] = []
        for row in audit.get("active_records") or []:
            if not isinstance(row, dict) or not row.get("workspace"):
                continue
            fields = {k: row[k] for k in BridgeRecord.__dataclass_fields__ if k in row}
            kept.append(BridgeRecord(**fields))
        removed_registry = len(load_records()) - len(kept)
        save_records(kept)

    if kill_orphans:
        for row in audit.get("orphan_processes") or []:
            pid = int(row.get("pid") or 0)
            if pid <= 0:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                killed.append(pid)
            except ProcessLookupError:
                pass
            except OSError:
                pass

    return {
        "removed_registry": removed_registry,
        "killed_pids": killed,
        "audit": audit_bridge_processes(),
    }
