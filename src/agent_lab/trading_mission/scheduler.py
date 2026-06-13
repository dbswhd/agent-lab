"""Trading Mission scheduler — premarket auto-run (P2)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_KST = timezone(timedelta(hours=9))
_DEFAULT_STATE = Path.home() / ".agent-lab" / "trading_mission_scheduler_state.json"


def _now_kst() -> datetime:
    return datetime.now(_KST)


def scheduler_state_path() -> Path:
    raw = (os.getenv("AGENT_LAB_TRADING_SCHEDULER_STATE") or "").strip()
    return Path(raw).expanduser() if raw else _DEFAULT_STATE


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


def scheduled_premarket_time() -> tuple[int, int]:
    """Return (hour, minute) in KST from AGENT_LAB_TRADING_SCHEDULE (default 07:30)."""
    raw = (os.getenv("AGENT_LAB_TRADING_SCHEDULE") or "0730").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 4:
        hour = int(digits[:2])
        minute = int(digits[2:4])
        return max(0, min(hour, 23)), max(0, min(minute, 59))
    return 7, 30


def is_premarket_due(*, now: datetime | None = None) -> bool:
    """True when local KST clock is at or after scheduled time today."""
    when = now or _now_kst()
    if when.tzinfo is None:
        when = when.replace(tzinfo=_KST)
    else:
        when = when.astimezone(_KST)
    hour, minute = scheduled_premarket_time()
    scheduled = when.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return when >= scheduled


def premarket_already_ran(state: dict[str, Any], *, day: str | None = None) -> bool:
    today = day or _now_kst().strftime("%Y-%m-%d")
    return str(state.get("last_premarket_date") or "") == today


def should_run_premarket(*, now: datetime | None = None, force: bool = False) -> bool:
    if force:
        return True
    when = now or _now_kst()
    if when.weekday() >= 5:
        return False
    if not is_premarket_due(now=when):
        return False
    state = _load_state(scheduler_state_path())
    return not premarket_already_ran(state)


def record_premarket_run(*, day: str | None = None, session_id: str | None = None) -> None:
    path = scheduler_state_path()
    state = _load_state(path)
    today = day or _now_kst().strftime("%Y-%m-%d")
    state["last_premarket_date"] = today
    state["last_premarket_at"] = _now_kst().isoformat()
    if session_id:
        state["last_session_id"] = session_id
    _save_state(path, state)


def run_premarket_subprocess(
    *,
    pipeline_root: str | Path | None = None,
    ingest: bool = False,
    mock_room: bool = False,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Invoke scripts/run_trading_mission_premarket.py as subprocess."""
    agent_lab_root = Path(__file__).resolve().parents[3]
    script = agent_lab_root / "scripts" / "run_trading_mission_premarket.py"
    if not script.is_file():
        return {"ok": False, "reason": f"script missing: {script}"}

    env = os.environ.copy()
    if pipeline_root:
        env["QUANT_PIPELINE_ROOT"] = str(Path(pipeline_root).expanduser().resolve())

    cmd = [sys.executable, str(script)]
    if ingest:
        cmd.append("--ingest")
    if mock_room:
        cmd.append("--mock-room")
    if extra_args:
        cmd.extend(extra_args)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(agent_lab_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": str(exc), "command": cmd}

    stdout = (proc.stdout or "").strip()
    session_id = None
    for line in stdout.splitlines():
        if line.startswith("session:"):
            session_id = line.split(":", 1)[1].strip()
            break

    ok = proc.returncode == 0
    if ok:
        record_premarket_run(session_id=session_id)
    return {
        "ok": ok,
        "returncode": proc.returncode,
        "session_id": session_id,
        "stdout_tail": stdout[-2000:] if stdout else "",
        "stderr_tail": (proc.stderr or "").strip()[-1000:],
        "command": cmd,
    }


def scheduler_tick(*, force: bool = False, **run_kwargs: Any) -> dict[str, Any]:
    """One scheduler poll — run premarket when due."""
    if not should_run_premarket(force=force):
        return {
            "ok": True,
            "skipped": True,
            "reason": "not_due_or_already_ran",
            "scheduled": scheduled_premarket_time(),
        }
    result = run_premarket_subprocess(**run_kwargs)
    result["skipped"] = False
    return result
