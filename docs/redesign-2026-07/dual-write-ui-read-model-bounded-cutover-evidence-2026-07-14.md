# UI read-model bounded cutover evidence — 2026-07-14

Todo 7 completed a reversible production-like cutover on the existing `:8765` service. The parity gate from Todo 6 was already green; the UI read-model flag was then enabled on a temporary restart with a non-empty allowlist (776 migrated session IDs, recorded by SHA-256 only).

## Result

- Temporary UI-on process: PID 14643, `AGENT_LAB_MISSION_UI_READ_MODEL=1`; health returned `ok=true`. The process used a non-empty full-inventory allowlist of 776 IDs (SHA-256 recorded in the task packet); the bounded soak verifier used a separate 15-ID allowlist.
- Bounded soak: 15 approved Room-turn fixtures plus one legacy sentinel. All 16 read-model requests returned valid JSON/HTTP 200; 15 were `migrated=true/source=mission_journal`, and the sentinel was `migrated=false/source=legacy`.
- Scoped verifier and journal audit were clean: `checked=15`, exactly equal to the bounded soak allowlist count; hard mismatch 0, missing 0, duplicate 0, invalid JSON 0, verifier errors 0, not-found 0. The 776-ID full-inventory allowlist was residual baseline evidence only and was not a GO gate.
- Browser checks against the live Vite proxy covered migrated and legacy sessions with zero console errors, uncaught page errors, or failed requests. Inbox backlog counters were all zero.

## Failure-first rollback and restoration

Before claiming soak success, the UI-on process was killed and restarted with `AGENT_LAB_MISSION_UI_READ_MODEL=0`. Migrated read-model remained reachable and the legacy sentinel returned `migrated=false`; journal, run, and allowlist hash diffs were all zero. The temporary Vite process and port were cleaned up. The pre-existing service state was then restored on `:8765`: dual-write and authority flags remained enabled, UI flag was unset/off, and the dual-write session allowlist was unset/empty. No writer or M6 authority was altered, and the legacy writer was not retired.

Full artifact details are in [`task-7.json`](../../.omo/evidence/wave-b-m6-retire/task-7.json); temporary redacted reports are under `/tmp/agent-lab-ui-read-model-cutover-20260714/`.

The 776-session verifier inventory contains hard mismatches/missing rows (39/15) outside the bounded 15-turn allowlist. The aggregate counts were identical before and after service restoration, so they are retained as residual baseline evidence and were not introduced by this cutover.
