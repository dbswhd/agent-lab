# Sprint D checklist

Track implementation of room coordination, provenance, and UI exposure items.

## HIGH priority

- [x] **D1 — Turn lead UI (`turn_leads`)** — `tasks_public_payload` exposes `turn_leads`; `RoomTaskBar` shows 이번 턴 리드 + compact 턴 리드 기록.
- [x] **D2 — Discuss mode task state scope** — `sync_tasks_after_turn` skips plan links / turn_state harvest on discuss-only; `should_assign_tasks_on_turn` gates pre-claim.
- [x] **D3 — Lead vs teammate role hardening** — `build_team_task_block` orchestration vs propose guidance; `lead_discuss_role_block` prepended for lead on discuss.
- [x] **D4 — Plan decision provenance** — `ROOM_SCRIBE` refs; `plan_provenance.py` extract/validate; plan tab ref click → chat line (existing `onRefClick`).
- [x] **D5 — Task completed ↔ verification** — `task_complete_block_reason` + artifact `execution:` refs; API `409`; tests in `test_room_tasks.py`.

## MEDIUM priority

- [x] **D6 — Discuss / plan UI mode exposure** — Composer mode chip (토론 / 정리·plan / 합의) + new vs continue hints.
- [x] **D7 — Task bar ↔ execute unified flow** — `RoomTaskBar` footer `plan #N ↔ task ↔ execution` rows.
- [x] **D8 — Agent-initiated claim** — Teammate claim hints; `auto_claim_tasks_from_turn` after turn (max 1/agent).

## LOW priority (minimal)

- [x] **D9 — Clarifier gate** — `AGENT_LAB_CLARIFIER=1`; `clarifier_prompt` SSE; `RoomChat` banner; skips agent round when triggered.
- [x] **D10 — R2 peer quality metrics** — `peer_turn_metrics` in turn snapshot (`peer_message_count`, `agents_with_r2_reply`).
- [x] **D11 — send receipt / schema** — `send_receipt` on turn snapshot + `complete` SSE; UI receipt from backend.

## Verification

- [x] `python -m pytest tests/ -q --ignore=tests/e2e` (176 passed)
- [x] `cd web && npm run build`
