from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


_JOURNAL_NAME = "mission-events.jsonl"


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


def _journal_events(folder: Path) -> tuple[dict[str, object], ...]:
    """Load events from the session mission journal.

    Each event is returned as a JSON-serializable dict containing
    ``event_cursor``, ``event_type`` and ``payload`` so that downstream
    consumers (including tests) can verify the SSE contract.
    """
    journal = folder / ".agent-lab" / _JOURNAL_NAME
    if not journal.is_file():
        return ()
    events: list[dict[str, object]] = []
    with journal.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("record_type") == "batch":
                raw_events = record.get("events", [])
            else:
                raw_events = [record]
            for raw in raw_events:
                events.append(
                    {
                        "event_cursor": raw.get("sequence"),
                        "event_type": raw.get("event_type"),
                        "payload": raw.get("payload", {}),
                    }
                )
    return tuple(events)


def _sse_event(payload: dict[str, object]) -> str:
    """Format a single SSE event with an ``id: <cursor>`` line."""
    event_id = payload.get("event_cursor")
    data = json.dumps(payload, ensure_ascii=False)
    return f"id: {event_id}\ndata: {data}\n\n"


@router.get("/sessions/{session_id}/mission/events")
def get_mission_events(
    session_id: str,
    request: Request,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Stream mission events from ``{session_folder}/.agent-lab/mission-events.jsonl``.

    The endpoint emits standard ``text/event-stream`` payloads with an
    ``id: <cursor>`` line per event.  When a ``Last-Event-ID`` header is
    supplied, events with a cursor greater than the supplied value are replayed
    first.  This matches the contract expected by ``consumeSse()`` in the web
    client, which parses ``data: ...`` lines and ignores the optional ``id``
    lines until reconnection.
    """
    folder = session_folder_or_404(session_id)
    after_cursor = _parse_event_id(last_event_id)

    def event_stream():
        events = _journal_events(folder)
        for event in events:
            cursor = event.get("event_cursor")
            if not isinstance(cursor, int) or cursor <= after_cursor:
                continue
            yield _sse_event(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
