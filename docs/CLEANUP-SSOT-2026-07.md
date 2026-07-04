# Cleanup SSOT — 2026-07 (한 페이지)

> **운영 모드:** dogfood-first (N1 formal closure **waived** — [CLEANUP-PHASE0-SCOPE-2026-07.md](./CLEANUP-PHASE0-SCOPE-2026-07.md))  
> **방향:** [NORTH-STAR.md](./NORTH-STAR.md) · **shipped:** [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md)

---

## 충돌 시 우선순위

1. **5모트** — BLOCK→409 · worktree · Oracle+Repair · run.json · Human Inbox  
2. **Mission lifecycle** (NORTH-STAR §2.3) — 루프 밖 기능 추가 금지  
3. **TRACEABILITY + code + tests** — 문서만 앞서면 문서를 고침  
4. **이 파일 + ROOM-TRANSCRIPT-CONTRACT** — Room UX 버그는 C1 계약 기준

---

## SSOT 표

| 주제 | Code SSOT | Doc SSOT | Dogfood 메모 |
|------|-----------|----------|--------------|
| Turn / preset | `turn_modes.py`, `roomPresets.ts` | [TURN-MODES.md](./TURN-MODES.md) | 실작업 **supervisor** (S1 trio implicit ON) |
| Topology / roles | `topic_router.py`, `role_plan.py` | [ROLE-ORCHESTRATION-PLAN.md](./ROLE-ORCHESTRATION-PLAN.md) | Settings 6버튼 UI **없음** |
| Room flow | `room/turn_flow*.py` | [FLOW.md](./FLOW.md) | |
| Transcript UX | `runSessionRegistry.ts`, `useRoomSseHandler.ts` | [ROOM-TRANSCRIPT-CONTRACT.md](./ROOM-TRANSCRIPT-CONTRACT.md) | Blocker **1a** |
| Persisted chat | `chat.jsonl` | — | final text only |
| Turn activity | `live_log` → `live_archives/` | ROOM-TRANSCRIPT-CONTRACT | merge on refresh |
| S1 flags | `s1_flags.py` | [DESIGN-S1-FEEDBACK-LOOP.md](./DESIGN-S1-FEEDBACK-LOOP.md) | KPI §1.4 NORTH-STAR; no D3 ceremony |
| run.json patch | `patch_run_meta()` | CLAUDE.md F4 · `test_run_meta_write_discipline.py` | no mid-turn disk reload |
| Structure waves | — | [STRUCTURE-REFACTOR-WAVE.md](./STRUCTURE-REFACTOR-WAVE.md) | Wave B ✅ · Phase D (1c) active |
| Shipped? | tests + smoke | TRACEABILITY | D3 language = closed only |

---

## 실행 순서 (2026-07 Human 확定)

```text
Now     supervisor dogfood · blocker fixes · F4 rule in CLAUDE.md
1a      Room transcript contract — `make test-c1`       ← done
1b      Wave B room/context split + F4 CI guard — **done** (`test_room_context_package`, `test_run_meta_write_discipline`)
1c      Phase D RoomChat hooks (5/5 wired) · client.ts split ← next
2w      N2 profile mapping · dead code §3.4 (1 PR each)
1mo     N4 UI (after 1c) · F7 repo_map decision
Q       §2.5 matrix · KPI review · N5/S2 re-eval (episode n≥30) — **no global task bandit**
```

**PR 규칙:** blocker 1개 또는 구조 1개 — S1 tuning + RoomChat refactor 같은 PR 금지.

---

## 실사용 운영 (3줄)

1. **Preset:** supervisor 고정 (`AGENT_LAB_TURN_METRICS` / `OUTCOME_LEDGER` / `FEEDBACK_ADVISOR` implicit ON).  
2. **버그:** 재현 1줄 (세션 id · `@agent` · spinner/activity/lock).  
3. **리포트:** `make feedback-report` — 마일스톤 때만 (매 PR gate 아님).

---

## Freeze (touch = explicit Human OK)

N5–N7 (S2 global bandit frozen) · Gateway · trading 이전 · preset 6 UI · N8/N9 · Room supervisor cleanup loop
