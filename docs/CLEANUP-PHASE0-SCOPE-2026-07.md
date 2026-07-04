# Cleanup Phase 0 — Scope (확정)

> **작성:** 2026-07-02 · **상태:** **Closed** → Phase **1a** active  
> **운영 모드:** **dogfood-first** — N1 formal “운영 닫힘” 의식 **waived** (Human 2026-07)  
> **한 페이지 SSOT:** [CLEANUP-SSOT-2026-07.md](./CLEANUP-SSOT-2026-07.md)  
> **방향:** [NORTH-STAR.md](./NORTH-STAR.md) · **구조:** [STRUCTURE-REFACTOR-WAVE.md](./STRUCTURE-REFACTOR-WAVE.md)

---

## 0. Human 결정 요약

| 항목 | 결정 |
|------|------|
| **N1 S1** | D3 closure ceremony **하지 않음**. `supervisor` 실사용 + S1 implicit ON + blocker fix on touch |
| **Keep (실행)** | **Phase 1a C1** → Phase 1c Phase D → Phase 1b Wave B |
| **Freeze** | N5–N7, Gateway, trading move, preset 6 UI, N8/N9 |
| **Phase 0** | Scope + SSOT + F4 rule + obsolete plan 삭제 → **closed** |

**dogfood-first 만료 (NORTH-STAR §1):** 분기 재검토 — `by_source.history.n` ≥ 30 episode 관측 시 N1 formal closure **재검토** (강제 아님).

---

## 1. Dogfood-first 운영 (N1 대체)

### 매일

- **Preset:** `supervisor` (S1 trio: `AGENT_LAB_TURN_METRICS`, `AGENT_LAB_OUTCOME_LEDGER`, `AGENT_LAB_FEEDBACK_ADVISOR` — `s1_flags.py`)
- **목표:** Mission lifecycle 쓰면서 blocker만 고침 — lift/report는 **참고용**

### 버그 기록 (1줄)

`재현 · session id · @mention · symptom` — 예: `@codex 후 3명 spinner → 무응답`

### PR 규칙

- **한 PR = blocker 1개** 또는 **구조 slice 1개**
- S1 튜닝 + RoomChat 대수술 **같은 PR 금지**
- 5모트 regression 깨지면 그날 feature 추가 금지

### 문서 언어

- S1 = **dogfood-active** (D3 “닫힘” 표현 금지 until 체감 또는 분기 만료 재검토)
- `make feedback-report` / `dogfood-feedback-mock` — CI 유지, **merge gate 아님**

---

## 2. 실행 순서 (확정)

```text
✅ Phase 0   scope · SSOT · F4 · ROOM-TRANSCRIPT-CONTRACT · obsolete plans 삭제
✅ Phase 1a  C1 transcript contract tests — `make test-c1`
✅ Phase 1b  Wave B — room/context/ split + F4 guard (`test_run_meta_write_discipline`)
→ Phase 1c  Phase D — RoomChat hooks (useRoomRunWatchdog · useRoomRecoveryLifecycle)
  Phase 1d  Wave C pipeline_* (if needed)
  Phase 1e  F5 trading 격리 (별 PR)
  Phase 2   dead code §4 (1 PR = 1 item)
  ~2w       N2 profile mapping (no full UI)
  ~1mo      N4 Autonomy UI · F7 repo_map ON or delete
  분기       N5+
```

**검증 (every PR):** `make test-fast` · `python scripts/smoke_room.py`

---

## 3. 충돌 시 우선순위

1. 5모트  
2. NORTH-STAR 6 concepts + §2.3 lifecycle  
3. TRACEABILITY + code + tests  
4. [ROOM-TRANSCRIPT-CONTRACT.md](./ROOM-TRANSCRIPT-CONTRACT.md)

---

## 4. C1~C6 — 현재 처方

| ID | 처方 | Phase |
|----|------|-------|
| C1 UI/SSE/registry | ROOM-TRANSCRIPT-CONTRACT + vitest | **1a** |
| C2 Default-OFF | supervisor dogfood; N2 later | dogfood |
| C3 doc drift | SSOT + NORTH-STAR gauge honest | ongoing |
| C4 run_meta | CLAUDE.md rule; single writer later | 0 + 1 |
| C5 RoomChat debt | Phase D before N4 UI | **1c** |
| C6 Room cleanup loop | **금지** | — |

---

## 5. Dead code / deprecate (Phase 2 queue)

| 후보 | Evidence / note |
|------|-----------------|
| ~~Legacy turn profile segmented picker~~ | ✅ `tests/test_phase2_dead_code.py` — UI absent |
| ~~Settings topology 6-button UI~~ | ✅ same — SettingsPage has no topology grid |
| `AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST=1` | **Keep** opt-in — default `0`, MCP-first (contract test) |
| API deprecated `mode`/`synthesize` branches | TURN-POLICY — `synthesize_only` still live; defer |
| ~~`artifacts/plans/agent-lab-*-direction.md` ×3~~ | **Deleted** — NORTH-STAR supersedes |

---

## 6. Out of scope (unchanged)

N5–N7 구현 · Mission Gateway 확장 · trading 이전 in core PR · preset 6 UI restore · Live LLM CI · Room supervisor mass cleanup

---

## 7. Phase 0 closure checklist

- [x] dogfood-first Human decision recorded  
- [x] [CLEANUP-SSOT-2026-07.md](./CLEANUP-SSOT-2026-07.md)  
- [x] [ROOM-TRANSCRIPT-CONTRACT.md](./ROOM-TRANSCRIPT-CONTRACT.md)  
- [x] F4 in CLAUDE.md  
- [x] NORTH-STAR S1 / §3.3 aligned  
- [x] Obsolete `artifacts/plans/agent-lab-*-direction.md` ×3 deleted  
- [x] §5 dead code grep evidence (Phase 2) — segmented picker · topology 6-button · harvest opt-in (`test_phase2_dead_code.py`); synthesize_only defer
- [x] Phase 1a: C1 vitest + live_log archive — `make test-c1`
- [x] Phase 1c: Phase D hook extractions + `client.ts` split (`http` · `workspaceClient` · `missionGatewayClient` · `wsClient`)  

---

## 8. Agent split

| Work | Agent |
|------|-------|
| Blocker fix / 1a–1c code | Cursor |
| Test failure triage | Codex + regression-check |
| Doc contradiction scan | Claude Ask |
| Architecture alternatives | Kimi Work (read-only) |
| **Not for cleanup** | Room supervisor loop |

---

*Next: dogfood on supervisor · file blockers against ROOM-TRANSCRIPT-CONTRACT · Phase 1c when 1a stable.*
