from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from agent_lab.mission.event_codec import decode_event
from agent_lab.mission.journal import JournalCorruptionError, MissionJournal, StoredEvent
from agent_lab.mission.kernel import MissionState, apply_event, new_mission

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


_JOURNAL_NAME = "mission-events.jsonl"
_TERMINAL_STATES = frozenset({MissionState.SUCCEEDED, MissionState.FAILED, MissionState.CANCELLED})
_POLL_SEC = 1.0
_KEEPALIVE_SEC = 15.0


def _parse_event_id(last_event_id: str | None) -> int:
    """Return the cursor after which events should be replayed (0 = from start)."""
    if last_event_id is None or last_event_id == "":
        return 0
    try:
        cursor = int(last_event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid Last-Event-ID")
    if cursor < 0:
        raise HTTPException(status_code=400, detail="invalid Last-Event-ID")
    return cursor


def _event_payload(stored: StoredEvent) -> dict[str, object]:
    return {
        "event_cursor": stored.sequence,
        "event_type": stored.event_type,
        "payload": dict(stored.payload),
    }


def _sse_event(payload: dict[str, object]) -> str:
    """Format a single SSE event with an ``id: <cursor>`` line."""
    event_id = payload.get("event_cursor")
    data = json.dumps(payload, ensure_ascii=False)
    return f"id: {event_id}\ndata: {data}\n\n"


def _mission_is_terminal(folder: Path, events: tuple[StoredEvent, ...]) -> bool:
    """Fold ``events`` through the mission kernel to check for a terminal state.

    ``goal`` is irrelevant to state transitions (``new_mission`` only stores it
    verbatim), so a placeholder is safe here — this call exists purely to
    decide whether the journal can still receive more events, not to build a
    real read model.
    """
    mission = new_mission(folder.name, folder.name)
    for stored in events:
        mission = apply_event(mission, decode_event(stored))
    return mission.state in _TERMINAL_STATES


async def mission_events_stream(
    folder: Path,
    *,
    after_cursor: int,
    is_disconnected: Callable[[], Awaitable[bool]],
    poll_sec: float = _POLL_SEC,
    keepalive_sec: float = _KEEPALIVE_SEC,
) -> AsyncIterator[dict[str, object] | None]:
    """Replay journal events after ``after_cursor``, then tail for new ones.

    Keeps polling ``mission-events.jsonl`` while the mission stays in a
    non-terminal state, yielding ``None`` as a periodic keepalive marker so a
    client can distinguish "still connected, nothing new yet" from a dropped
    connection. Extracted from the route so tests can drive it directly with a
    fake ``is_disconnected`` instead of a real ASGI disconnect (mirrors
    ``_room_resume_events`` in ``room.py``).
    """
    journal_path = folder / ".agent-lab" / _JOURNAL_NAME
    if not journal_path.is_file():
        return
    journal = MissionJournal(journal_path)
    cursor = after_cursor
    last_keepalive = time.monotonic()
    while True:
        if await is_disconnected():
            return
        try:
            events = journal.recover_tail()
        except JournalCorruptionError:
            return
        newest = events[-1].sequence if events else 0
        if newest > cursor:
            for stored in events:
                if stored.sequence <= cursor:
                    continue
                yield _event_payload(stored)
            cursor = newest
            last_keepalive = time.monotonic()
        if _mission_is_terminal(folder, events):
            return
        now = time.monotonic()
        if now - last_keepalive >= keepalive_sec:
            last_keepalive = now
            yield None
        await asyncio.sleep(poll_sec)


@router.get("/sessions/{session_id}/mission/events")
async def get_mission_events(
    session_id: str,
    request: Request,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Stream mission events from ``{session_folder}/.agent-lab/mission-events.jsonl``.

    The endpoint emits standard ``text/event-stream`` payloads with an
    ``id: <cursor>`` line per event. When a ``Last-Event-ID`` header is
    supplied, events with a cursor greater than the supplied value are
    replayed first. After replay, the connection is held open and the journal
    is tailed for new events while the mission remains in a non-terminal
    state; the stream closes once the mission reaches a terminal state
    (SUCCEEDED/FAILED/CANCELLED) or the client disconnects.
    """
    folder = session_folder_or_404(session_id)
    after_cursor = _parse_event_id(last_event_id)

    async def generate() -> AsyncIterator[str]:
        async for event in mission_events_stream(
            folder,
            after_cursor=after_cursor,
            is_disconnected=request.is_disconnected,
        ):
            yield ": keepalive\n\n" if event is None else _sse_event(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
