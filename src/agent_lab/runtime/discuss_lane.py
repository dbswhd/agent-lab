"""Discuss lane handlers — scribe / plan pipeline side effects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.runtime.dispatch_result import DispatchResult
from agent_lab.runtime.events import RuntimeEvent


def handle_scribe_complete(folder: Path, payload: dict[str, Any]) -> DispatchResult:
    from agent_lab.mission.loop import after_plan_scribe

    plan_md = payload.get("plan_md")
    if not isinstance(plan_md, str):
        return DispatchResult(handled=False, reason="missing plan_md")
    result = after_plan_scribe(folder, plan_md)
    if result is None:
        return DispatchResult(handled=True, skipped=True, reason="mission_loop_inactive")
    phase = str(result.get("phase") or "") if isinstance(result, dict) else None
    return DispatchResult(handled=True, result=result, phase=phase)


_DISCUSS_HANDLERS = {
    RuntimeEvent.SCRIBE_COMPLETE: handle_scribe_complete,
}


def dispatch_discuss_event(
    folder: Path,
    event: RuntimeEvent,
    payload: dict[str, Any] | None = None,
) -> DispatchResult:
    handler = _DISCUSS_HANDLERS.get(event)
    if handler is None:
        return DispatchResult(handled=False, reason=f"unsupported discuss event: {event}")
    return handler(folder, payload or {})
