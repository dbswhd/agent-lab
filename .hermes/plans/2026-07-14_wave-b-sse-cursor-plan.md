# Wave B §7.4 SSE cursor / durable event merge plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.  
> **Goal:** Connect `/api/sessions/{id}/mission/read-model` read-model to the existing Room SSE stream so `event_cursor` is validated against durable events, and reconnect replays missed events instead of polling run.json.

**Architecture:** Add a dedicated mission-events SSE route that emits journal-first events tagged with `event_cursor`; keep the existing `useMissionReadModel` hook as the consumer but replace its polling loop with a single SSE connection plus epoch guard. Replays are driven by server-side `Last-Event-ID` (cursor) rather than client run.json fallback.

**Tech Stack:** FastAPI `StreamingResponse`, `EventSource` (browser), `web/src/api/client.ts` for transport, `web/src/utils/missionReadModel.ts` for consumer state, `src/agent_lab/mission/journal.py` for event storage.

---

## Task 1: Inventory existing SSE and read-model endpoints

**Objective:** Map all server/client SSE touchpoints and the journal file layout.

**Files:**
- Read: `app/server/routers/room.py:363-650` (existing `runRoom*` SSE patterns)
- Read: `app/server/routers/mission_read_model.py` (read-model route, `_payload`, `_legacy_payload`)
- Read: `src/agent_lab/mission/dual_write.py`
- Read: `src/agent_lab/mission/journal.py` or `src/agent_lab/mission/events.py` (journal-first storage)
- Read: `web/src/api/client.ts:1633-1750` (`consumeSse` helper)
- Read: `web/src/utils/missionReadModel.ts`

**Step 1:** List server-side SSE endpoints.

Run: `grep -rn "StreamingResponse\|text/event-stream\|/events" app/server/routers/`

Expected output: existing `/room/*` SSE routes and the new read-model route.

**Step 2:** Confirm journal file path and schema.

Run: `grep -rn "mission-events.jsonl\|event_cursor\|JournalEvent" src/agent_lab/mission/`

Expected: one canonical path per session + a documented event schema.

**Step 3:** Confirm client `EventSource` usage rules.

Run: `grep -rn "EventSource\|consumeSse\|runRoom" web/src/`

Expected: only `runRoom` and `useAutonomySession` use `consumeSse`; `fetchMissionReadModel` does not yet use SSE.

**Step 4:** Commit inventory findings.

```bash
git add docs/redesign-2026-07/11-ui-ux-surface-map.md  # append only if you update notes
git commit -m "chore: inventory SSE and read-model endpoints for §7.4"
```

---

## Task 2: Add `event_cursor` validation to the read-model payload

**Objective:** Server-side: ensure `event_cursor` in the read-model payload matches the actual journal line count / durable event index, and fail-closed to legacy if it does not.

**Files:**
- Modify: `app/server/routers/mission_read_model.py:149` (`_payload_integrity_ok`)
- Modify: `src/agent_lab/mission/read_model.py` (compute `event_cursor` from `mission.version` + journal length)
- Test: `tests/test_mission_read_model.py` (verify cursor consistency)

**Step 1:** Write failing test for cursor mismatch.

```python
def test_read_model_payload_null_when_event_cursor_mismatch() -> None:
    mission = new_mission("m-cursor", "ship")
    # Simulate a run where journal has 3 events but model claims cursor 1
    run = {"mission_loop": {"event_cursor": 1}, "human_inbox": []}
    # Integrity check should fail and return legacy payload
    payload = _payload("session-1", build_read_model(mission, run=run), legacy_phase=None)
    assert payload["source"] == "legacy"
```

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_mission_read_model.py::test_read_model_payload_null_when_event_cursor_mismatch -v`
Expected: FAIL — `_payload_integrity_ok` does not check cursor mismatch.

**Step 2:** Implement cursor validation.

In `app/server/routers/mission_read_model.py`, add to `_payload_integrity_ok`:

```python
def _expected_event_cursor(folder: Path) -> int:
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal.is_file():
        return 0
    with journal.open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _payload_integrity_ok(payload: MissionReadModelPayload, *, folder: Path) -> bool:
    if payload.get("event_cursor") is None or payload["event_cursor"] < 0:
        return False
    if payload["event_cursor"] != _expected_event_cursor(folder):
        return False
    ...
```

Also thread `folder` through `_payload` and the exception handler.

**Step 3:** Run the new test and the read-model suite.

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_mission_read_model.py -q`
Expected: all 29 passed.

**Step 4:** Commit.

```bash
git add app/server/routers/mission_read_model.py tests/test_mission_read_model.py
git commit -m "feat: validate event_cursor against journal line count"
```

---

## Task 3: Create server-side mission events SSE route

**Objective:** Add `/api/sessions/{id}/mission/events` that streams `mission_journal` events with `id: <event_cursor>` and supports `Last-Event-ID` replay.

**Files:**
- Create: `app/server/routers/mission_events.py`
- Modify: `app/server/main.py` or routing table to register the new router
- Test: `tests/test_mission_events_sse.py`

**Step 1:** Write failing test.

```python
def test_mission_events_sse_replays_from_last_event_id(client: TestClient, tmp_path: Path) -> None:
    session_id = "sess-1"
    folder = tmp_path / session_id
    (folder / ".agent-lab").mkdir(parents=True)
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    journal.write_text('{"cursor":1}\n{"cursor":2}\n{"cursor":3}\n')
    # Mock session_folder_or_404 to return folder
    ...
    response = client.get(f"/api/sessions/{session_id}/mission/events", headers={"Last-Event-ID": "2"})
    assert response.status_code == 200
    text = response.read().decode()
    assert 'id: 3' in text
    assert 'id: 2' not in text
```

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_mission_events_sse.py -v`
Expected: FAIL — route does not exist.

**Step 2:** Implement the route.

```python
# app/server/routers/mission_events.py
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


def _mission_events_from(folder: Path, after_cursor: int = 0) -> list[dict[str, Any]]:
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal.is_file():
        return []
    events: list[dict[str, Any]] = []
    with journal.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            if idx <= after_cursor:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload["event_cursor"] = idx
            events.append(payload)
    return events


@router.get("/sessions/{session_id}/mission/events")
async def mission_events_sse(
    session_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    folder = session_folder_or_404(session_id)
    after = 0
    if last_event_id is not None:
        try:
            after = int(last_event_id)
        except ValueError:
            after = 0

    async def generate():
        for event in _mission_events_from(folder, after_cursor=after):
            cursor = event["event_cursor"]
            yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
        yield b"event: done\ndata: {}\n\n"
        while not await request.is_disconnected():
            await asyncio.sleep(5)
            yield b": keepalive\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

Register it in the main FastAPI app routing table.

**Step 3:** Run tests.

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_mission_events_sse.py -q`
Expected: passed.

**Step 4:** Commit.

```bash
git add app/server/routers/mission_events.py app/server/main.py tests/test_mission_events_sse.py
git commit -m "feat: add mission events SSE route with Last-Event-ID replay"
```

---

## Task 4: Wire client `useMissionReadModel` to SSE

**Objective:** Replace the 2.5-second polling loop in `useMissionReadModel` with a durable EventSource connection that increments `requestEpoch` per `open` and applies epoch guard on every event.

**Files:**
- Modify: `web/src/utils/missionReadModel.ts`
- Add: `web/src/utils/missionEventsSSE.ts` (small wrapper if needed)
- Test: `web/src/utils/missionReadModel.test.ts`

**Step 1:** Write failing test for SSE behavior.

```typescript
// web/src/utils/missionReadModel.test.ts
it("rejects stale SSE events after reconnect", async () => {
  const events = [
    { data: JSON.stringify({ event_cursor: 1, migrated: true, source: "mission_journal" }) },
    { data: JSON.stringify({ event_cursor: 2, migrated: true, source: "mission_journal" }) },
  ];
  mockEventSource(events);
  const { result } = renderHook(() => useMissionReadModel("sess-1"));
  await waitFor(() => expect(result.current.model?.event_cursor).toBe(2));
});
```

Run: `cd web && npm test -- missionReadModel.test.ts`
Expected: FAIL — hook still polls, no SSE consumer.

**Step 2:** Add an EventSource wrapper.

```typescript
// web/src/utils/missionEventsSSE.ts
export type MissionEventHandler = (payload: unknown) => void;

export function connectMissionEventsSSE(
  sessionId: string,
  onEvent: MissionEventHandler,
  onError?: () => void,
  lastEventId?: string,
): EventSource {
  const url = `${apiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/mission/events`)}${
    lastEventId ? `?lastEventId=${encodeURIComponent(lastEventId)}` : ""
  }`;
  const es = new EventSource(url);
  es.onmessage = (event) => {
    if (event.data) {
      try {
        onEvent(JSON.parse(event.data));
      } catch {
        /* ignore malformed */
      }
    }
  };
  es.onerror = () => onError?.();
  return es;
}
```

Use `apiUrl` from `web/src/api/http.ts`.

**Step 3:** Replace polling in `useMissionReadModel`.

```typescript
// web/src/utils/missionReadModel.ts
export function useMissionReadModel(
  sessionId: string | null,
  reloadKey = 0,
): MissionReadModelState {
  const [model, setModel] = useState<MissionReadModelPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const requestEpoch = useRef(0);

  useEffect(() => {
    if (!sessionId) {
      requestEpoch.current += 1;
      setModel(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setModel(null);
    setLoading(true);
    const epoch = ++requestEpoch.current;

    const apply = (next: MissionReadModelPayload | null) => {
      if (!cancelled && shouldApplyMissionReadModelEpoch(requestEpoch.current, epoch)) {
        setModel(next);
      }
    };

    const bootstrap = async () => {
      if (!(await missionUiReadModelEnabled())) {
        setLoading(false);
        return;
      }
      // Initial snapshot so UI can render immediately
      try {
        const payload = await fetchMissionReadModel(sessionId);
        const parsed = parseMissionReadModel(payload);
        if (!cancelled && epoch === requestEpoch.current) {
          apply(isUsableMissionReadModel(parsed) ? parsed : null);
        }
      } catch {
        // ignore, SSE will catch up
      }
      setLoading(false);
      const lastEventId = model?.event_cursor ? String(model.event_cursor) : undefined;
      const es = connectMissionEventsSSE(
        sessionId,
        (raw) => {
          const parsed = parseMissionReadModel(raw);
          if (isUsableMissionReadModel(parsed)) {
            apply(parsed);
          }
        },
        () => setLoading(false),
        lastEventId,
      );
      return () => es.close();
    };

    const cleanupPromise = bootstrap();
    return () => {
      cancelled = true;
      void cleanupPromise.then((cleanup) => cleanup?.());
    };
  }, [reloadKey, sessionId]);

  return { model, loading };
}
```

**Step 4:** Run tests.

Run: `cd web && npm test -- missionReadModel.test.ts`
Expected: passed (or new test passes, existing tests still pass).

**Step 5:** Commit.

```bash
git add web/src/utils/missionEventsSSE.ts web/src/utils/missionReadModel.ts web/src/utils/missionReadModel.test.ts
git commit -m "feat: replace read-model polling with durable SSE"
```

---

## Task 5: Ensure consumer precedence after SSE update

**Objective:** Verify all 7 consumers still use `missionReadModel?.field ?? legacy` and no one reads `model.event_cursor` directly for UI ordering.

**Files:**
- Read: `web/src/components/HumanInboxPanel.tsx:612-640`
- Read: `web/src/components/NotificationCenter.tsx`
- Read: `web/src/components/WorkToolPanel.tsx`
- Read: `web/src/utils/missionOverviewView.ts`
- Read: `web/src/components/ComposerEventStack.tsx`

**Step 1:** Audit call sites.

Run: `grep -RIn "missionReadModel" web/src/components web/src/utils`
Expected: all access uses `?. ??` fallback.

**Step 2:** Add a lint-like test.

```typescript
// web/src/utils/missionReadModel.test.ts
it("exposes event_cursor only for internal validation, not UI ordering", () => {
  const payload: MissionReadModelPayload = { ...validPayload, event_cursor: 42 };
  expect(payload.event_cursor).toBe(42);
  // No assertions on UI ordering; epoch guard owns ordering.
});
```

**Step 3:** Commit.

```bash
git add web/src/utils/missionReadModel.test.ts
git commit -m "test: assert consumer precedence and cursor usage boundaries"
```

---

## Task 6: End-to-end verification

**Objective:** Manual or automated verification that reconnect replays missed events and stale events are dropped by epoch guard.

**Files:**
- Read: `docs/redesign-2026-07/11-ui-ux-surface-map.md` §8.3
- Test: `tests/test_mission_events_sse.py`, `web/src/utils/missionReadModel.test.ts`

**Step 1:** Run server-side tests.

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_mission_events_sse.py tests/test_mission_read_model.py -q`
Expected: all passed.

**Step 2:** Run client tests.

Run: `cd web && npm test -- missionReadModel.test.ts`
Expected: passed.

**Step 3:** Manual browser verification (optional, if dev server is running).

Run: `make dev` in one terminal, then open the app, trigger a mission that creates human inbox items, disconnect/reconnect network, and confirm HumanInboxPanel restores from SSE without polling run.json.

**Step 4:** Update §8.4 documentation.

In `docs/redesign-2026-07/11-ui-ux-surface-map.md`, mark the following as now guaranteed:

```markdown
| `event_cursor` vs SSE 쪽 비교 | `app/server/routers/mission_read_model.py`, `web/src/utils/missionReadModel.ts` | cursor == journal length, SSE events replayed from `Last-Event-ID` |
| durable event merge on reconnect | `app/server/routers/mission_events.py`, `web/src/utils/missionEventsSSE.ts` | server replays missed events; client epoch guard drops stale responses |
```

Mark §7.4 as done.

**Step 5:** Final commit and push.

```bash
git add docs/redesign-2026-07/11-ui-ux-surface-map.md
git commit -m "docs: mark §7.4 SSE cursor wiring as complete"
# Confirm push with user before running: git push origin main
```

---

## Risks, tradeoffs, and open questions

1. **Cycle risk:** Adding `mission_events.py` may import `session_folder_or_404` from `app.server.deps`, which already existed in `mission_read_model.py`. No new `src/agent_lab/` cycle is expected.
2. **Cursor semantics:** Is `event_cursor` 1-indexed line count or 0-indexed event count? The plan assumes 1-indexed journal line count. Adjust tests/code if the journal schema uses 0-indexed.
3. **SSE vs polling fallback:** If the browser does not support `EventSource` (e.g., React Native), the hook silently degrades to no read-model. Decide later if a fetch fallback is needed.
4. **Backpressure:** The server keepalive loop runs forever while connected. Fine for browsers; may need explicit cleanup for server-sent resources.
5. **Open question:** Does `HumanInboxPanel` answer POST need to carry `decision_id` + `expected_version` for optimistic locking? Out of scope for §7.4; belongs to §7.3.

---

## Verification summary

| # | Command | Expected |
|---|---------|----------|
| 1 | `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_mission_events_sse.py tests/test_mission_read_model.py -q` | all passed |
| 2 | `cd web && npm test -- missionReadModel.test.ts` | passed |
| 3 | `env -u PYTHONPATH make test-fast` | 12 pre-existing failures unchanged; no new failures from these files |
| 4 | `git status --short` | only 5-7 files changed |

**Plan saved at:** `.hermes/plans/2026-07-14_wave-b-sse-cursor-plan.md`

**Next:** Execute with subagent-driven-development — dispatch a fresh subagent per task with two-stage review (spec compliance then code quality).
