"""Boulder / resume state + last_failure SSOT (H6)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_lab.run.meta import patch_run_meta, read_run_meta

RuntimeLane = Literal["execute", "mission", "discuss", "control"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_bucket(run: dict[str, Any]) -> dict[str, Any]:
    rt = run.get("runtime")
    return rt if isinstance(rt, dict) else {}


def last_failure(run: dict[str, Any]) -> dict[str, Any] | None:
    lf = runtime_bucket(run).get("last_failure")
    return lf if isinstance(lf, dict) else None


def boulder_state(run: dict[str, Any]) -> dict[str, Any] | None:
    """Resume checkpoint — prefers runtime.boulder, falls back to mission last_partial."""
    b = runtime_bucket(run).get("boulder")
    if isinstance(b, dict) and b.get("resume_phase"):
        return b
    ml = run.get("mission_loop") if isinstance(run.get("mission_loop"), dict) else {}
    if str(ml.get("phase") or "") != "MISSION_PAUSED":
        return None
    partial = ml.get("last_partial") if isinstance(ml, dict) else None
    if not isinstance(partial, dict):
        return None
    resume_phase = partial.get("resume_phase")
    if not resume_phase:
        return None
    return {
        "resume_phase": resume_phase,
        "phase_before": partial.get("phase"),
        "action_index": partial.get("action_index"),
        "execution_id": partial.get("execution_id"),
        "at": partial.get("at"),
        "source": "last_partial",
        "reason": partial.get("reason"),
    }


def record_last_failure(
    folder: Path,
    *,
    lane: RuntimeLane,
    event: str,
    reason: str,
    phase: str | None = None,
    action_index: int | None = None,
    execution_id: str | None = None,
    recoverable: bool = True,
    resume_phase: str | None = None,
) -> dict[str, Any]:
    failure = {
        "at": _now_iso(),
        "lane": lane,
        "event": event,
        "reason": (reason or "").strip()[:500],
        "phase": phase,
        "action_index": action_index,
        "execution_id": execution_id,
        "recoverable": recoverable,
        "resume_phase": resume_phase,
    }

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        rt = dict(runtime_bucket(run))
        rt["last_failure"] = failure
        run["runtime"] = rt
        return run

    patch_run_meta(folder, _patch)
    return failure


def clear_last_failure(folder: Path) -> None:
    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        rt = dict(runtime_bucket(run))
        rt.pop("last_failure", None)
        if rt:
            run["runtime"] = rt
        else:
            run.pop("runtime", None)
        return run

    patch_run_meta(folder, _patch)


def sync_boulder(
    folder: Path,
    *,
    resume_phase: str,
    phase_before: str | None = None,
    action_index: int | None = None,
    execution_id: str | None = None,
    source: str,
    reason: str | None = None,
) -> dict[str, Any]:
    checkpoint = {
        "resume_phase": resume_phase,
        "phase_before": phase_before,
        "action_index": action_index,
        "execution_id": execution_id,
        "at": _now_iso(),
        "source": source,
        "reason": reason,
    }

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        rt = dict(runtime_bucket(run))
        rt["boulder"] = checkpoint
        run["runtime"] = rt
        return run

    patch_run_meta(folder, _patch)
    return checkpoint


def sync_boulder_from_partial(folder: Path, *, source: str = "pause") -> dict[str, Any] | None:
    run = read_run_meta(folder)
    ml = run.get("mission_loop") if isinstance(run.get("mission_loop"), dict) else {}
    partial = ml.get("last_partial") if isinstance(ml, dict) else None
    if not isinstance(partial, dict):
        return None
    resume_phase = str(partial.get("resume_phase") or "").strip()
    if not resume_phase:
        return None
    return sync_boulder(
        folder,
        resume_phase=resume_phase,
        phase_before=str(partial.get("phase") or "") or None,
        action_index=partial.get("action_index"),
        execution_id=str(partial.get("execution_id") or "").strip() or None,
        source=source,
        reason=str(partial.get("reason") or "") or None,
    )


def clear_boulder(folder: Path) -> None:
    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        rt = dict(runtime_bucket(run))
        rt.pop("boulder", None)
        if rt:
            run["runtime"] = rt
        else:
            run.pop("runtime", None)
        return run

    patch_run_meta(folder, _patch)
