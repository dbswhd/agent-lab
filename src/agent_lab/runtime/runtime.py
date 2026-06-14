"""Agent Lab unified runtime dispatcher (H2 execute lane write path)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.runtime.dispatch_result import DispatchResult
from agent_lab.runtime.events import RuntimeEvent
from agent_lab.runtime.discuss_lane import dispatch_discuss_event
from agent_lab.runtime.execute_lane import dispatch_execute_event
from agent_lab.runtime.mission_lane import dispatch_control_event, dispatch_mission_event


def dispatch(
    folder: Path,
    event: RuntimeEvent | str,
    payload: dict[str, Any] | None = None,
) -> DispatchResult:
    """Route a runtime event to the appropriate lane handler."""
    if isinstance(event, str):
        event = RuntimeEvent(event)
    if event.value.startswith("execute."):
        return dispatch_execute_event(folder, event, payload)
    if event.value.startswith("scribe.") or event.value.startswith("turn."):
        return dispatch_discuss_event(folder, event, payload)
    if event.value.startswith("mission."):
        return dispatch_mission_event(folder, event, payload)
    if event == RuntimeEvent.RUN_CANCEL:
        return dispatch_control_event(folder, event, payload)
    return DispatchResult(handled=False, reason=f"no handler for {event.value}")


def dispatch_verify_result(
    folder: Path,
    *,
    action_index: int,
    verdict: str,
    reason: str = "",
    oracle: dict[str, Any] | None = None,
) -> DispatchResult:
    """Convenience wrapper for merge-time Oracle verdict."""
    verdict_norm = str(verdict or "").strip().lower()
    event = RuntimeEvent.EXECUTE_VERIFY_PASS if verdict_norm == "pass" else RuntimeEvent.EXECUTE_VERIFY_FAIL
    return dispatch(
        folder,
        event,
        {
            "action_index": action_index,
            "verdict": verdict_norm,
            "reason": reason,
            "oracle": oracle,
        },
    )
