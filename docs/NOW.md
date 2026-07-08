# NOW — 지금 무엇을 해야 하는가 (종합 상태 표면)

> **작성:** 2026-07-08 · **갱신:** 2026-07-08 (코드 트랙 우선 결정) · **역할:** 핵심 5문서를 종합해 "오늘/이번 주/다음/동결"을 **한 곳**에서 판정한다.
> **이 문서가 아닌 것:** 방향·설계·참조의 SSOT가 아니다 — 그건 아래 4문서. 이 문서는 **상태 포인터**만 갖는다.
> **ID 규칙:** 새 ID를 만들지 않는다. 소스 문서의 ID(P0-4, F7, N4, HS0 …)를 그대로 쓰고 출처를 병기한다.
> **진실 순서:** 코드 > 이 문서 > 개별 문서의 상태 표기. 여기 상태는 커밋/명령 출력으로 검증된 것만 적는다.

---

## 0. 핵심 5문서 지도 — 언제 무엇을 읽나

| 문서 | 역할 (한 줄) | 읽는 시점 |
|------|--------------|-----------|
| [NORTH-STAR.md](./NORTH-STAR.md) | 방향·완성도 게이지·D0~D4 판정 언어·흡수 매트릭스 SSOT | 방향/우선순위 논쟁이 생길 때, 분기 리뷰 |
| [WORKFLOW-DYNAMIC-REFERENCE.md](./WORKFLOW-DYNAMIC-REFERENCE.md) | 4과정 구조·동적 적응 등급·파일 치트시트 — **작업 착수 참조** | 코드 수정 PR 시작 전 (§6 해당 절 + §12 체크리스트) |
| [EVAL-SURFACE-SUPER-SAMPLE-PLAN.md](./EVAL-SURFACE-SUPER-SAMPLE-PLAN.md) | **§Canonical Definitions만 현행** (episode·MIN_SAMPLE·null lift) — 나머지는 완료 이력 | episode/lift 수치를 해석할 때 |
| [DESIGN-HARNESS-SELF-IMPROVE.md](./DESIGN-HARNESS-SELF-IMPROVE.md) | N6 Phase 2 HSIL 설계 (DRAFT) — HS0~HS7 로드맵 | HS 작업 착수 시 |
| [REVIEW-LINER-RESEARCH-2026-07.md](./REVIEW-LINER-RESEARCH-2026-07.md) | Liner 연구 6종 검토 — HSIL 수정 P0(5)·P1(5)·P2(3)·기각(6) 목록 | HSIL DRAFT→APPROVED 판정 시, HS3~HS5 착수 전 |

우선순위 ID가 문서마다 겹친다(P0~P2 vs P0-1~P0-5 vs P1~P3 vs HSIL D1~D7 vs **REVIEW P0-1~P0-5**). **충돌 시 이 문서 §1 큐의 정렬이 실행 순서다.**

---

## 1. 실행 큐 (정렬 = 실행 순서)

> **Human 결정 (2026-07-08):** dogfood를 제대로 돌릴 만큼 개발이 성숙하지 않았다고 판단 — **지금 할 수 있는 코드 작업을 우선**한다. dogfood/운영 트랙(구 큐 1~3)은 §「보류 — dogfood 재개 시」로 이동. 재개 시점도 Human이 결정.

### 지금 — 코드 트랙 (전부 mock-only 검증 가능, dogfood 불필요)

HS0~HS5 전부(HS5-1~7·B1-B4 포함) ✅ 07-08~07-09 shipped (Impl **Tier B**, Human 명시 확인 후 착수).
커밋 `6325c845`(merge_gate.py 코어) + HS5-3 후속 커밋(Tier A + L2 경량 승인 —
`autonomy_promotion.harness_patch_light_approval_eligible`, 오토노미 레벨 L2+일 때만 Tier A
`used_light_approval` 허용, Tier B는 여전히 full Inbox만).

HS6/HS7은 design doc상 "동결 until HS-M5"(HS6) / "동결 until HS6 평가"(HS7) — HS-M5 게이트가 실제
Human 승인 1건(라이브 세션, mock 아님)을 요구하므로 **dogfood 보류 결정과 충돌**한다. 착수는 별도
Human 확인 후.

**2026-07-09 착수 검토 결과 (기각):** `.agent-lab/outcomes.jsonl` 실사용 236건 전수 확인 —
`primary_tag` 태깅된 행 **0건**(recurrence 미달이 아니라 후보 자체가 없음). HS1-1 실패 태깅은
Room 세션의 `harness_infra`(Oracle skipped)/`false_success`(근거 없는 pass)/`weak_taste`(미해결
BLOCK 또는 턴당 CHALLENGE≥2) 3개 신호로만 발동하는데 지금까지 하나도 발생한 적이 없음. 인위적으로
만들면 HS-M5의 취지(진짜 반복 약점을 harness가 스스로 고쳤는가) 훼손 — 기각. **재검토 트리거**:
`make feedback-report JSON=1` 확인 시마다 `scripts/propose_harness.py --mode list`도 함께 확인 —
addressable 패턴이 뜨면 그때 HS-M5 착수 재논의.

**큐 비어 있음** (2026-07-09) — 문서 정비 백로그(§4)는 2026-07-08자로 이미 표 소진 완료, HS0~HS5(+HS5-3)도 전부 shipped. HS6은 위 검토대로 보류. 다음 코드 트랙 항목은 §1 재검토 트리거(HS-M5 addressable 패턴, 또는 새 Human 지시) 발생 시 여기 추가.

### 보류 — dogfood 재개 시 (구 「지금」 큐 — 닫힘 기준 불변)

| 항목 | 소스 ID | 비고 |
|------|---------|------|
| **F7 ON/OFF 결정** — ⏰ ~~2026-07-12~~ | NORTH-STAR **F7** | **시한 충돌**: dogfood 보류로 07-12 결정 불가. 「방치 금지」 조항과 충돌하므로 **기본값 유지 or 시한 연장을 Human이 명시 결정해야 함** — 이 행이 닫히기 전까지 F7 플래그는 현 기본값 고정 |
| S1 lift + explore dogfood | WORKFLOW **P0-5** · NORTH-STAR **N1** | `by_source.history.n` ≥ 3 · explore > 0 (live) — 기준 불변 |
| N4 D3 증거 누적 | NORTH-STAR **§1.4.1** | dogfood 편승 항목 — 단독 재개 없음 |
| Composer preset 제거 | WORKFLOW §8.2 **P2** | S1~S3 eval green 선행 = dogfood 의존 |

### 분기 리뷰 묶음 (한 세션에서 일괄 — NORTH-STAR §3.3 분기 행)

① `AGENT_LAB_QUARTER_BUDGET_USD` 실값 + `make f8-cost-report` 정례화 ② §2.5 흡수 매트릭스 재검토 ③ §1.4 KPI 리뷰 ④ N5/S2 재평가 ⑤ dogfood-first 만료 검토 (`history.n` ≥ 30) ⑥ ADR rebuild 재평가 (§3.5).

### 동결 — explicit Human OK 없이 착수 금지

N5 전역 bandit · N7/S3 구현(설계만 ✅) · HS6/HS7 · HSIL Tier D 전체 · Gateway · trading core 표면 · `fork_time_minutes` 자동화(N8 잔여, P3).

---

## 2. shipped 확인 대장 (문서보다 앞선 코드)

개별 문서에 아직 반영 안 된 shipped 상태. **문서를 읽다 여기와 충돌하면 이쪽이 맞다.**

| 항목 | 증거 | 낡은 문서 위치 |
|------|------|----------------|
| P0-1~P0-3 (clarity 앵커 · TurnSignals · FSM bootstrap 스킵) | 커밋 `5a3fc000` | — |
| **P0-4** live S1 1턴 재검증 | 세션 `…-room.py에서-consensus-라운드-cap-기본값이-뭐야-14` (2026-07-08): `init/advance_plan_workflow=false` · `plan_workflow` 없음 · `turns=1` · latency 57s | WORKFLOW §8.2.1 P0-4 행 |
| P1 TurnContract 스냅샷 → `run.json` `turn_policy` | 커밋 `0f41dfe5` | — |

---

## 3. 판정 명령 (전체 모음은 WORKFLOW §13)

```bash
make test-fast && python scripts/smoke_room.py   # 회귀 (코드 트랙 큐 1~4 — 매 변경)
make ci                       # HS0 닫힘 기준 (큐 1)
make feedback-report JSON=1   # harness_attribution 확인 (큐 1) · S1 lift는 보류 트랙
python scripts/propose_harness.py --mode list   # HS-M5 재검토 트리거 (§1 HS6 기각 사유) — addressable 뜨면 재논의
make eval-surface-local       # T0/T1 supersample (evals/results/latest.json)
make f7-dogfood-report        # 보류 — F7 재개 시
```

---

## 4. 문서 정비 백로그 (핵심 문서 피드백 — 별도 정비 PR용, 코드 작업과 분리)

**2026-07-08 전부 ✅ 반영 완료** — NORTH-STAR(D-라벨 정정·§3.1/§3.4 수치 통일·앵커 맵 명령 참조화·N2/N6/N10 이력 §3.3.1 3차 wave 이동), WORKFLOW(P1 TurnContract ✅·§9/§2.5 SSOT 분리 명시), EVAL-PLAN(헤더 현행 가치 명시·"부족한 부분" 재분류), HSIL(§15 HS-M1~M7 개명·§8.4 스키마 복원). 근거는 각 소스 문서에 남음 — 이 문서는 포인터만 유지하므로 상세 이력 없음.

---

## 5. 이 문서의 운영 방법

- **갱신 트리거:** 큐 항목이 닫히거나 시한(⏰)이 지나면 즉시. 최소 주 1회 큐 재정렬.
- **갱신 방법:** 닫힌 항목은 행 삭제 + 소스 문서(NORTH-STAR §3.1 등)에 판정 근거를 남긴다. 이력은 여기 쌓지 않는다 — 이 문서는 항상 짧아야 한다 (~150줄 상한).
- **금지:** 여기서 새 설계·새 ID·새 KPI를 만들지 않는다. 그런 내용이 필요하면 소스 문서를 고치고 여기는 포인터만 갱신.
