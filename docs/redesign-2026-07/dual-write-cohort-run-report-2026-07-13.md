# Dual-write cohort run report — 2026-07-13

> **v3d 판정: GO** — [v3d 섹션](#v3d-operational-cohort-go)  
> **v2 판정: NO-GO (coverage)** — execute/merge duplicate **NOT PROVEN**  
> **v1 판정: NO-GO** — [v1 섹션](#v1-판정-2026-07-13-nogo)

## v3d operational cohort (GO)

| 단계 | 결과 |
| --- | --- |
| Traffic (live HTTP, `sessions/dw-c3d-*`) | **PASS** — allowlist **151** · execute-resolve **42** · merge-confirm **42** · reverify **42** · `hard_mm=0` · journal duplicate **0** · health mirrored ≥500 (approve 84 · merge 42 · oracle 42) |
| 61분 watch | **PASS** — 15 ticks · `hard_failure_ticks=0` · span **3,660s** · clean span **3,660s** (2026-07-14 03:47–04:48 KST) |
| Rollback (`DUAL_WRITE=0`) | **PASS** — 신규 세션 journal 미생성 · mirrored 세션 read-model 정상 |

산출물: `/tmp/agent-lab-dw-cohort3d/` (`reports/final.json`, `ledger/watch.jsonl`, `cohort-allowlist.txt`)

### v3d gate 판정

| 기준 | 판정 | 근거 |
| --- | --- | --- |
| 100 dual-writes (operational) | **PASS** | 동일 process·allowlist·`sessions/` · route quota 포함 mirrored ≥100 |
| 60분 관찰 (clean baseline 후) | **PASS** | ledger/clean span **3,660s** · final tick · `hard_failure_ticks=0` |
| unexplained mismatch = 0 | **PASS** | baseline + watch 전체 `hard_mm=0` |
| missing write = 0 | **PASS** | `inbox_create` errors **0** · merge-conflict gate open/close bridge |
| unexpected duplicate = 0 | **PASS** | `mission_dual_write_journal_audit.py` `duplicate_count=0` on allowlist 151 |
| execute/merge/reverify coverage | **PASS** | quota 강제 · 각 경로 ≥42 세션 |
| startup eager recovery | **PASS** | traffic startup `reason=startup`, `errors=0` |
| `DUAL_WRITE=0` rollback | **PASS** | `reports/rollback.json` |

**v3d 수정:** absolute sessions/repos path · merge-confirm orphan gate close · traffic route quotas · journal duplicate audit.

**GO 범위:** controlled cohort evidence만. **다음 Human gate = Full traffic (bounded cutover + soak)** — [full-traffic runbook](./dual-write-full-traffic-bounded-cutover-2026-07-14.md). Legacy writer retire는 soak 이후 **별도** 승인 전 금지 ([ADR-001](../decisions/ADR-001-production-dual-write-cutover.md)).

---

## v2 operational cohort (완료 — NO-GO coverage)

| 단계 | 결과 |
| --- | --- |
| Traffic (live HTTP, `sessions/dw-c2-*`) | **PASS** — health mirrored **173** · response-count **100** · `inbox_create` errors **0** · baseline `hard_mm=0` (allowlist 75세션) |
| 61분 watch | **PASS** — 15 ticks · `hard_failure_ticks=0` · span **3,660s** · clean span **3,660s** (2026-07-13 22:39–23:40 KST) |
| Rollback (`DUAL_WRITE=0`) | **PASS** — 신규 세션 journal 미생성 · mirrored 세션 read-model 정상 |

스크립트: `scripts/mission_dual_write_operational_cohort.py`  
산출물: `/tmp/agent-lab-dw-cohort2/` (`reports/{traffic,operational,rollback}.json`, `ledger/watch.jsonl`)

### v2 gate 판정

| 기준 | 판정 | 근거 |
| --- | --- | --- |
| 100 dual-writes (operational) | **PASS** | 동일 process·allowlist·`sessions/`에서 health mirrored **173** ≥ 100 |
| 60분 관찰 (clean baseline 후) | **PASS** | ledger/clean span **3,660s** · final tick 포함 · `hard_failure_ticks=0` |
| unexplained mismatch = 0 | **PASS** | watch 15 ticks 전부 `hard_mm=0` |
| missing write = 0 | **PASS** | `mission_journal_missing` **0** (journal 선행 inbox만) |
| unexpected duplicate = 0 | **NOT PROVEN** | traffic이 plan/inbox 위주; `execute/merge/reverify` operational 표본 부족 |
| startup eager recovery | **PASS** | traffic report `reason=startup`, `errors=0` |
| `DUAL_WRITE=0` rollback | **PASS** | `reports/rollback.json` |

**v2 변경:** 합성 `/tmp` 합산 없음 · `merge-confirm` 제외(orphan inbox) · allowlist 오염 방지(`env -u AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS`).

**다음 cohort:** operational 100건에 `execute/resolve`·`reverify` 포함 + duplicate 감사; `merge-confirm` orphan inbox 수정 후 재포함 검토.

---

## v1 판정 (2026-07-13 NO-GO)
> Human cutover evidence ledger: 2026-07-13 operational cohort (12 sessions, ad-hoc local uvicorn, mock agents)

## Gate 판정 (authoritative)

| 기준 | 판정 | 근거 |
| --- | --- | --- |
| 100 dual-writes | **FAIL** | 100건은 격리 `/tmp` 합성; operational은 12세션·logged mirrors 13. 합성 verify `exit 1`, hard mismatch 10. |
| 60분 관찰 | **FAIL** | ledger span **3,301s (55m01s)**; 첫 mismatch 해소 후 clean span **3,001s (50m01s)** — 둘 다 60분 미만. |
| unexplained mismatch = 0 | **PASS (caveat)** | 관측 mismatch는 원인 설명됨 — 단 explained missing write는 별도 gate 실패. |
| missing write = 0 | **FAIL** | legacy question 1건이 Mission gate 없이 pending; `mission_journal_missing` 시도 **3회** (cohort 실패 사유, 제외 아님). |
| unexpected duplicate = 0 | **NOT PROVEN** | operational journal 12개에서 duplicate 미발견; execute/merge/Oracle 대표 표본 부족. |
| startup eager recovery | **PASS** | `reason=startup`, `errors=0` (ledger + health). |
| `DUAL_WRITE=0` rollback | **PASS** | 신규 세션 journal 없이 approve; 기존 mirrored 세션 read-model 정상. |

**FSM contract (별도 기록):** `mission_not_ready_to_execute` **0건** — 약속대로 실패에 포함하지 않음. targeted tests **81 passed**.

외부 evidence 요약: `agent-lab-cutover-evidence-2026-07-13.json` (Codex outputs, 2026-07-13).

## 무엇이 돌았는가

| 단계 | 결과 | 비고 |
| --- | --- | --- |
| 합성 100 route ops | route 루프 PASS · verify **hard_mm=10** | `/tmp/agent-lab-dw-cohort-20260713/` — **operational cohort에 합산 불가** |
| Live API `DUAL_WRITE=1` | startup recovery PASS | cohort 전용 local uvicorn `:8765` |
| Live HTTP `plan/approve` ×10 | mirrored×10 | `dw-cohort-op-01..10` |
| Room dogfood ×2 | plan approve mirrored×2 | CLARIFY 선행 inbox → `mission_journal_missing` ×3 |
| 60분 watch | 12 ticks · `hard_failure_ticks=1` (tick 1) | ledger: `/tmp/.../ledger/watch.jsonl` |
| Rollback | PASS | `DUAL_WRITE=0` 재기동 + smoke |

## 실패 원인 (다음 cohort에서 막을 것)

1. **합성 ≠ operational** — 100건은 동일 allowlist·동일 live process·동일 `sessions/` identity에서 세어야 함.
2. **관찰 창** — mismatch 해소 **이전** tick부터 세지 말 것; **clean baseline 확정 후** 60분+ 및 **종료 시점 final tick** 필수.
3. **`mission_journal_missing`** — Room CLARIFY 등 journal 생성 전 inbox는 **missing write**. 발생 시 **해당 evidence window 폐기 후 재시작** (수동 resolve로 복구한 뒤 계속 세면 안 됨).
4. **경로 커버리지** — 이번 operational은 주로 `plan/approve`; execute/merge/Oracle duplicate 감사는 미증명.

## 다음 cohort 요구사항 (재시도 SSOT)

1. **동일 operational cohort** (전용 process + allowlist)에서 **dual-write 100건** — 합성 `/tmp` 루프 별도 집계 금지.
2. **Clean baseline** — `verify --cohort` `hard_mm=0` 확인 후 watch 시작.
3. **관찰 ≥60분** — ledger 전체 span 및 clean span 모두 3,600s 이상; **마지막 tick**에 final verify 포함.
4. **`mission_journal_missing` 0** — 1건이라도 발생하면 window 폐기·cohort 재시작.
5. **rollback + startup recovery** — 이번과 동일 스모크 재실행.
6. **execute/merge/Oracle** — 대표 route를 operational 100건에 포함해 duplicate gate 증명.

## 산출물 경로

- ledger: `/tmp/agent-lab-dw-cohort-20260713/ledger/watch.jsonl`
- reports: `/tmp/agent-lab-dw-cohort-20260713/reports/{synthetic,live_routes}.json`
- cohort sessions (정리 전): `sessions/dw-cohort-op-*`, `sessions/2026-07-13-dw-cohort-kimi-*`

## 스크립트

- `scripts/mission_dual_write_synthetic_cohort.py` — pre-flight/격리용만; **cutover 100건 증거로 사용 금지**
- `scripts/mission_dual_write_live_routes.py`
- `scripts/mission_dual_write_cohort_watch.py`
- `scripts/mission_dual_write_rollback_smoke.py`

## 관련 문서

- [cutover scope limitations](./dual-write-cutover-scope-limitations-2026-07-13.md)
- [controlled cohort runbook](./dual-write-controlled-cohort-runbook-2026-07-13.md)
- [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md)
