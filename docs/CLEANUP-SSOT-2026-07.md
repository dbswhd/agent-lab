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
| Structure waves | — | [STRUCTURE-REFACTOR-WAVE.md](./STRUCTURE-REFACTOR-WAVE.md) | Wave B ✅ · Phase D (1c) ✅ |
| Autonomy Ladder | `autonomy_ladder.py`, `autonomy_inbox.py`, `useAutonomySession.ts` | NORTH-STAR N4 v1/v2 | PATCH ceiling · demotion inbox T-A0 ✅ |
| Run profiles (N2/F2) | `run/profile.py` (`flags`+`owns`) | NORTH-STAR N2 · F2 | feature 전수 소속 · `list-flags --profile` ✅ |
| F7 context quality | `repo_map.py` · `message_trim.py` | [F7-REPO-MAP-COMPACTION-DOGFOOD.md](./F7-REPO-MAP-COMPACTION-DOGFOOD.md) | protocol + report ready · decision pending |
| F8 cost visibility | `cost_ledger.py` · `cost_ledger_quarter.py` | [F8-COST-VISIBILITY.md](./F8-COST-VISIBILITY.md) | quarter rollup + L0 demote · `make f8-cost-report` ✅ |
| run_meta writes (F4) | `run/meta.py` (`stamp_run_meta`) · `test_run_meta_write_discipline.py` | CLAUDE.md · AGENTS.md | allowlist **empty** ✅ |
| Trading lane (F5) | `extensions/quant_trading.py` | [F5-TRADING-ISOLATION.md](./F5-TRADING-ISOLATION.md) | core PR trading delta 0 ✅ |
| Shipped? | tests + smoke | TRACEABILITY | D3 language = closed only |

---

## 실행 순서 (2026-07 Human 확定)

```text
✅ 1a–1c · Phase 2 · N2/N4 · F2/F4/F5/F6 · §3.2.1 · synthesize_only · F7/F8 prep
Now     S1 supervisor dogfood (optional) · `make feedback-report`
1mo     F7 **run** 7d · `make f7-dogfood-report` · ON/OFF decision
Q       §2.5 · KPI · F8 `QUARTER_BUDGET_USD` ops · N5/S2 re-eval (n≥30)
Freeze  N5–N7 · Gateway · trading core
```

See NORTH-STAR §3.3.1 for the full shipped table.

**PR 규칙:** blocker 1개 또는 구조 1개 — S1 tuning + RoomChat refactor 같은 PR 금지.

---

## 실사용 운영 (3줄)

1. **Preset:** supervisor 고정 (`AGENT_LAB_TURN_METRICS` / `OUTCOME_LEDGER` / `FEEDBACK_ADVISOR` implicit ON).  
2. **버그:** 재현 1줄 (세션 id · `@agent` · spinner/activity/lock).  
3. **리포트:** `make feedback-report` — 마일스톤 때만 (매 PR gate 아님).

---

## Freeze (touch = explicit Human OK)

N5–N7 (S2 global bandit frozen) · Gateway · trading 이전 · preset 6 UI · N8/N9 · Room supervisor cleanup loop
