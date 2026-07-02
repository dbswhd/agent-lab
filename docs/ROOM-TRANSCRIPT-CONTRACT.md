# Room transcript — client/server contract

> **Phase:** Cleanup 1a (C1 blocker) · **SSOT index:** [CLEANUP-SSOT-2026-07.md](./CLEANUP-SSOT-2026-07.md)  
> **Tests:** `make test-c1` — `web/src/run/runningAgents.test.ts`, `runSessionRegistry.test.ts`, `sessionChatMerge.test.ts`, `agentMentions.test.ts`, `tests/test_room_live_log.py`

Room UI bugs (spinners, missing activity, wrong agent count) come from breaking this contract — not from “agent didn’t reply.”

---

## 1. Two layers of truth

| Layer | SSOT | Holds |
|-------|------|--------|
| **Server persist** | `sessions/<id>/chat.jsonl` | Final message text, system/agent rows, envelopes |
| **Turn activity** | `live.jsonl` (in-flight) → `live_archives/turn-NNNN.jsonl` after persist | tool/thought SSE trail merged into UI `turnItems` |
| **Client live** | `runSessionRegistry` per `sessionId` | Typing bubbles, `topologyActive` / `topologyDone`, `localSseRun` |

**Rule:** Never hydrate server chat over an active local SSE turn unless `isSessionRunActive` is false and `localSseRun` is false.

---

## 2. SSE lifecycle (client)

1. **Send** — `resetTurnRun()` → `localSseRun: true`, `running: true`, user message in `turnMessages`.  
2. **Events** — `useRoomSseHandler` patches typing rows; `agent_start` / `agent_done` / `agent_error` finalize agents.  
3. **Lock gap** — Server yields `start` before run lock; `syncSessionFromServerLock` must **not** clear state while `localSseRun`.  
4. **Complete** — `complete` clears typing + `localSseRun`; `finishSessionRun()` in `executeSend` finally.  
5. **Refresh** — `sessionToMessages` + `mergePersistedChatWithLiveLog` + archived `live_log`; strip stale `typing` when run inactive.

---

## 3. Pending agent UI

| State | UI |
|-------|-----|
| `typing` bubble exists | Show `ReplyWaitingBubble` for that agent only |
| No typing, before first `agent_start` | **No** roster-wide placeholders |
| `topologyActive` set | At most **one** pending slot |
| `@codex` in user body | `effectiveTurnAgents()` — pending roster matches server mention filter |
| Some agents in `topologyDone` | Pending = not done, not typing |

Implementation: `derivePendingReplyAgents()` in `web/src/run/runningAgents.ts`.

---

## 4. Cancel / error

- User stop → `finalizeCancelledTyping()` (keep partial + `_(취소됨)_` if body/items exist).  
- Server cancel → `agent_done` with cancelled body or system row with `sourceAgent` on hydrate.  
- Lock released without SSE → `clearOrphanedRunState` only when **not** `localSseRun`.

---

## 5. Regression scenarios (must stay green)

1. **Lock poll during send** — `localSseRun` keeps `running` until terminal SSE.  
2. **Refresh after turn** — `turnItems` restored from archived live log.  
3. **`@codex` send** — single pending/typing for Codex, not full roster.  
4. **Cancelled system row** — no duplicate typing from live log replay (`sourceAgent` key).  
5. **Complete event** — no orphaned typing dots after turn ends.

---

## 6. When changing this area

Touch together (same PR when possible):

- `web/src/run/runSessionRegistry.ts`  
- `web/src/hooks/useRoomSseHandler.ts`  
- `web/src/utils/sessionChatMerge.ts`  
- `web/src/run/runningAgents.ts`  
- `src/agent_lab/room/live_log.py` (archive on persist)

Run: `cd web && npm test -- --run src/run/runningAgents.test.ts src/utils/sessionChatMerge.test.ts src/utils/agentMentions.test.ts`
