# Production route dual-write adapter — 2026-07-13

## Status

Implemented as an opt-in, fail-open migration slice. Set `AGENT_LAB_MISSION_DUAL_WRITE=1` on the API process to append Mission events after the legacy route succeeds. The default remains off.

## Route coverage

| Legacy route | Mission bridge | Idempotency boundary |
| --- | --- | --- |
| `POST /sessions/{id}/plan/approve` | `PlanOpened` + `PlanApproved` | plan hash |
| `POST /sessions/{id}/plan/reject` | `PlanOpened` + `PlanRejected` | plan hash + note |
| `POST /sessions/{id}/inbox/{item}/resolve` | `BlockResolved` when Mission is awaiting Human | item id + answer |
| `POST /sessions/{id}/execute/resolve` | execution start → diff ready → diff approved; returned commit SHA also records `MergeCommitted` | execution id + commit SHA |
| `POST /sessions/{id}/execute/merge/confirm` | `MergeCommitted` | execution id + commit SHA |
| `POST /sessions/{id}/execute/reverify` | `RecordMerge` + `RecordOracle` | execution id + verdict/detail |

The legacy writer remains first. Bridge failures are returned as `mission_dual_write.mirrored=false` and do not turn a successful legacy operation into an HTTP failure. This keeps rollback safe while evidence is collected. `VERIFYING` remains correct after merge because Oracle verification is still outstanding; parity is measured by `merged_commit_sha` and event cursor.

## Validation completed

- `tests/test_mission_dual_write.py`: opt-in behavior, plan idempotency, Human resume, scheduler enqueue idempotency, committed side-effect crash recovery.
- Existing route/profile/read-model/SSE suites: 69 passed.
- Isolated 10-session cohort: 5 scenarios × 2, parity/replay/reconnect/Inbox/side-effect all passed.
- Live uvicorn smoke on `127.0.0.1:8876`: health, Mission read-model, SSE resume from cursor 0 and 1, and flag discoverability passed.
- FastAPI route smoke with `AGENT_LAB_SESSIONS_DIR` isolated and dual-write enabled: `POST /plan/approve` returned `200`, `mirrored=true`, and read-model returned `READY_TO_EXECUTE`, `event_cursor=2`.
- Scheduler shadow enqueue validation: two consecutive runs produced `translation_parity=true`, `queue_parity=true`, `missing=0`, `unexpected=0`.

## Boundary

The initial real `sessions/` route cohort is recorded in [dual-write-route-cohort-report](./dual-write-route-cohort-report-2026-07-13.md). That cohort alone was sufficient only for a controlled opt-in GO because it did not cover Oracle fail→repair or daemon/crash. The follow-up evidence now covers actual Room dogfood, fail→repair with `RepairScheduled`, and recovery/health wiring; see [dual-write-cutover-followup](./dual-write-cutover-followup-2026-07-13.md) and [ActivityQueue auto-recovery](./activity-queue-auto-recovery-2026-07-13.md). The approve bridge records a returned merge commit in the same call; merge/confirm and reverify remain the fallback when the commit is not known at resolve time.
