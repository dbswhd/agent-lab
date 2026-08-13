# NOW — 지금 무엇을 해야 하는가 (종합 상태 표면)

> **작성:** 2026-07-08 · **갱신:** 2026-07-23 (Composer Decision Queue rebaseline) · **역할:** "오늘/이번 주/다음/동결"을 한 곳에서 판정한다.
> **이 문서가 아닌 것:** 방향·구조·턴·평가 계약의 SSOT가 아니다. 이 문서는 **상태 포인터**만 갖는다.
> **Browser acceptance:** Wave B/browser evidence is **accepted** (2026-07-24). Live proof: [wave-b-browser-acceptance-2026-07-24.md](redesign-2026-07/evidence/wave-b-browser-acceptance-2026-07-24.md). Mock/API suites remain regression, not a substitute for that live packet.
> **ID 규칙:** 소스 namespace를 보존한다 (`N*`, `F*`, `HS*`, `TC-*`, `ABS-P2-*`). bare `P1/P2` 신규 사용 금지.
> **진실 순서:** runtime 동작은 code+tests, 현재 상태는 NOW, 방향·구조·턴·평가는 아래 담당 문서가 각각 소유한다.

---

## 0. 현재 핵심 5문서

| 문서 | 역할 (한 줄) | 읽는 시점 |
|------|--------------|-----------|
| **[NOW.md](./NOW.md)** | 현재 실행 큐·시한·동결·Human 결정 | 작업을 시작하거나 재개할 때 |
| [NORTH-STAR.md](./NORTH-STAR.md) | 장기 방향·5모트·D0~D4·N/F 로드맵·해제 조건 | 방향이나 우선순위를 결정할 때 |
| [FLOW.md](./FLOW.md) | 현재 Discuss→Plan→Execute→Verify 구조와 Human gate | 시스템 경로를 파악할 때 |
| [TURN-CONTRACT.md](./TURN-CONTRACT.md) | TurnPolicy·TurnContract·cold start·history·safety 권한 | Room 턴 제어를 변경할 때 |
| [EVAL-CONTRACT.md](./EVAL-CONTRACT.md) | episode·표본·trace·grader·T0~T2 판정 | 결과와 lift를 해석할 때 |

`WORKFLOW-DYNAMIC-REFERENCE`, `EVAL-SURFACE-SUPER-SAMPLE-PLAN`, `DESIGN-HARNESS-SELF-IMPROVE`, `REVIEW-LINER-RESEARCH-2026-07`은 각각 history/reference 또는 feature spec이다. 현재 상태의 권위로 사용하지 않는다.

---

## 1. 실행 큐 (정렬 = 실행 순서)

### 지금 — Mission redesign continuation (Human 지시 2026-07-12)

| 단계 | 상태 | 다음 |
| --- | --- | --- |
| Step 0 authority/baseline | ✅ 완료 | 문서 상태·canonical 링크 유지 |
| Step 1 Mission application adapter | **철회 (2026-08-14)** | dual-write 브릿지는 어떤 run profile에서도 활성화된 적이 없다(`DUAL_WRITE` 미설정 → plan/execution write authority 항상 False). 브릿지 모듈·플래그 4종·테스트/스크립트 전량 제거. plan·execute 쓰기는 `run.json`이 단일 권위로 확정. Inbox만 저널 권위(Step 6–7). 이력: [controlled cohort runbook](./redesign-2026-07/evidence/dual-write-controlled-cohort-runbook-2026-07-13.md) |
| Step 2 MissionReadModel/UI contract | **browser acceptance accepted (2026-07-24)** | Live packet [wave-b-browser-acceptance-2026-07-24.md](redesign-2026-07/evidence/wave-b-browser-acceptance-2026-07-24.md). Mock `wave-b-journey.spec.ts` remains CI regression. |
| Step 3 Decision Queue vertical slice | ✅ route + Room dogfood + optimistic locking (2026-07-15) | production Human Inbox route와 실제 Room dogfood 2건 통과; `decision_id`/`mission_id`/`expected_version` 라운드트립으로 stale/중복 answer는 409 — `MissionApplication.guard_inbox_answer`. run.json 쓰기와의 완전 원자성(single transaction)은 여전히 별도 트랙 |
| Step 4 Execute/merge/Oracle | ✅ route parity + repair event | merge parity·fail→repair·RepairScheduled bridge·G3 process kill/restart 통과 |
| Step 5 Durable runtime hardening | ✅ shadow + fault pass | scheduler ActivityQueue validation, committed-side-effect restart recovery; production daemon opt-in remains |
| Step 6–7 bounded authority/read-model cutover | **Wave B Decision Queue browser-accepted; full-traffic Mission authority cutover ✅ 2026-07-25** (`SESSIONS=*`; M6 hard-delete still frozen) | `AGENT_LAB_MISSION_AUTHORITY=1` + non-empty `AGENT_LAB_MISSION_AUTHORITY_SESSIONS` 세션은 Inbox item open/resolve와 execution gate를 Mission journal 한 batch로 기록하며 `run.json` Inbox writer를 건너뛴다. `AGENT_LAB_MISSION_UI_READ_MODEL` 기본값은 `1`. Decision Queue live journeys are accepted (2026-07-24). M6 hard delete와 full-traffic 전환은 아직 금지하며 Human이 full cutover를 판정한다. |

**안전 경계 (2026-08-14 갱신):** 저널 권위는 **Inbox 슬라이스 하나뿐**이다. `AGENT_LAB_MISSION_AUTHORITY`(+ non-empty allowlist; `small`/`balanced`/`thorough`/`autonomous`가 `1` + `SESSIONS=*`)가 켜진 세션은 Inbox item open/resolve와 execution gate를 Mission journal에 기록하고 `run.json` Inbox writer를 건너뛴다. 빈 allowlist는 여전히 비활성. **plan·execute 쓰기는 `run.json`이 단일 권위**이며 이관 트랙은 철회됐다(Step 1). `AGENT_LAB_MISSION_UI_READ_MODEL` 기본값 `1`. M6 hard delete는 동결 유지. [journal-first design](./redesign-2026-07/evidence/journal-first-read-projection-design-2026-07-14.md).

**알려진 갭:** harvest 경로(`room/session_persist.py`)로 append된 Inbox 아이템은 저널 게이트를 열지 않는다 — read-model이 `run.json`을 병합하므로 목록에는 보이지만 `open_execution_gates`에는 빠진다. 회귀로 고정: `tests/test_mission_inbox_authority.py::test_authority_harvested_item_opens_a_journal_gate` (xfail strict).

> **Human 결정 (2026-07-08):** dogfood를 제대로 돌릴 만큼 개발이 성숙하지 않았다고 판단 — **지금 할 수 있는 코드 작업을 우선**한다. dogfood/운영 트랙(구 큐 1~3)은 §「보류 — dogfood 재개 시」로 이동.
> **Human 결정 (2026-07-09):** 코드 트랙 큐 소진 확인(아래) 후 **보류 해제 — dogfood 재개**. F7 7일 시계 재시작(`make dogfood-track-f7-start` → start_date=2026-07-09, 마감 2026-07-16 — 경과한 07-12 시한은 이 재시작으로 대체). 아래 §「지금 — 라이브 dogfood 트랙」이 신규 실행 큐.

### 기록 — 코드 트랙 (07-08~07-09, historical shipped claims; current browser acceptance 아님)

HS0~HS5 전부(HS5-1~7·B1-B4 포함) ✅ 07-08~07-09 shipped (Impl **Tier B**, Human 명시 확인 후 착수).
커밋 `6325c845`(merge_gate.py 코어) + HS5-3 후속 커밋(Tier A + L2 경량 승인 —
`autonomy_promotion.harness_patch_light_approval_eligible`, 오토노미 레벨 L2+일 때만 Tier A
`used_light_approval` 허용, Tier B는 여전히 full Inbox만).

HS6/HS7은 design doc상 "동결 until HS-M5"(HS6) / "동결 until HS6 평가"(HS7). **HS-M5는 2026-07-25 닫힘**
(`pc-2026-07-24-fc0b8932`, merge `755c38d9`) — HS6 자동 착수는 금지, 별도 Human 확인 후.

**2026-07-09 착수 검토 결과 (기각):** `.agent-lab/outcomes.jsonl` 실사용 236건 전수 확인 —
`primary_tag` 태깅 행 **0건**. **후속 코드 리뷰(같은 날)로 원인 정정:** ① 236행 중 235행이 HS1-1
배포(07-08) *이전* 데이터 — `weak_taste` 조건(턴당 CHALLENGE≥2)은 과거 4번 실발생(CH=5·3·3·2),
계측만 있었으면 태깅됐음. ② `false_success`는 구조적 사각지대였음(Oracle 판정은 턴 종료 *후*
execute에서 나오는데 태그는 턴 행에서만 도출 — turn 행 197개 중 195개 `final_verdict=null`) —
**수정 완료**: `derive_execution_failure_tags` 공유 헬퍼로 execute 행에서도 태깅. 결론 불변: 인위
생성은 기각, 실사용 누적 대기. **재검토 트리거**: `make feedback-report JSON=1` 확인 시마다
`scripts/propose_harness.py --mode list`도 함께 확인 — addressable 패턴이 뜨면 HS-M5 착수 재논의.

**2026-07-09 추가 shipped**: HS0-4 `harness_reproducibility_pp`(preset A/B swap — `make dogfood-suite-reproducibility`,
`feedback_report.py` 소비) · HS4-2 완료(`_TAG_TOPIC_MAP` 3개 태그 전부 근거 topic 확보 — 신규 X5/X6
dogfood 시나리오). 둘 다 mock-only, dogfood 무관.

**큐 비어 있음** (2026-07-09, historical snapshot) — 문서 정비 백로그(§4)는 당시 표 소진, HS0~HS5(+HS5-3, HS0-4, HS4-2)도 당시 code evidence 기준 shipped였다. 이는 현재 Wave B/browser acceptance를 의미하지 않는다. HS6은 위 검토대로 보류.

**2026-07-09 dogfood 재개 인프라:** `scripts/dogfood_progress.py` + `make dogfood-progress` / `dogfood-progress-auto` — suite-log 진행도 + X1(mission)·X2(plan→execute→Oracle) mock 자동. Human gate는 우회하지 않음(approve 명시 호출).

**2026-07-09 통합 트랙 (live-first):** `scripts/dogfood_track.py` + `make dogfood-track-run` — NOW 보류 큐(P0-5 · F7 · N4-D3 · CATALOG · HS-M5 · N1-30)를 **live supervisor**로 채운다. mock은 `dogfood-track-run-mock` 선택만.

### 지금 — 라이브 dogfood 트랙 (`scripts/dogfood_track.py`, `make dogfood-track` 재확인)

**2026-07-25 기준 6/6 닫힘** (`make dogfood-track` 재실행 결과; 아래 표는 이 스냅샷으로 갱신 — 문서가 낡으면 `make dogfood-track` 실측이 맞다):

| 게이트 | 소스 ID | 상태 | 다음 |
|--------|---------|------|------|
| **P0-5** S1 lift + explore | WORKFLOW **P0-5** · NORTH-STAR **N1** | ✅ 닫힘 (live ledger) | — |
| **F7** repo_map/compaction ON/OFF | NORTH-STAR **F7** | ✅ **닫힘 (ON, 2026-07-25)** — n=32 · coverage 100% · median budget 18.9. 프로필 `small`/`balanced`/`thorough`/`autonomous`에 flags ON. **거의 최종:** Human usefulness 체크리스트는 얇음 → non-lift 실사용 누적 후 한 번 재검토 ([F7 doc](./F7-REPO-MAP-COMPACTION-DOGFOOD.md) Revisit) | 재검토만 (limbo 아님) |
| **N4-D3** escalation_rate_by_level n≥10/level | NORTH-STAR **§1.4.1** | ✅ 닫힘 (2026-07-25) — L0/L1/L2/L3 = 3063/318/**10**/308. 루트픽스: turn-end `run_meta`가 `autonomy`/`trust_budget` 보존 (`SESSION_META_KEYS`). 증거: [phase-c1-n4-d3-2026-07-25.md](./redesign-2026-07/evidence/phase-c1-n4-d3-2026-07-25.md) | Phase C C1–C3 ✅ (M6 hard-delete 여전히 동결) |
| **CATALOG** dogfood-v1 suite coverage | — | ✅ 닫힘 | — |
| **HS-M5** addressable + Human harness_patch merge 1건 | — | ✅ 닫힘 (2026-07-25) — `pc-2026-07-24-fc0b8932` (`fp:weak_taste:deep`) → merge `755c38d9`. 증거: [phase-c3-hs-m5-2026-07-25.md](./redesign-2026-07/evidence/phase-c3-hs-m5-2026-07-25.md) | HS6 재개 여부는 Human 재논의 (자동 착수 금지) |
| **N1-30** dogfood-first 만료 검토 (history.n≥30) | — | ✅ 닫힘 (live ledger `eligible=812`, `by_source.history.n=236`) | — |

**N4-D3 L2 인프라 블로커 (닫힘 이력):** `scripts/l2_escalation_dogfood_live_repeat.py` / X2-lift 픽스처 경로에서 관측된 이슈 (해당 스크립트들은 2026-07-30에 삭제됨 — 아래는 이력 보존용):

- **(1) ask_human 배선 충돌 — 수정 완료** (`1ae16030`, `AGENT_LAB_PLAN_INBOX=1`).
- **(2) 재시도 메시지 / scratch plan scrub — harness 보강** (`_retry_topic`, `_scrub_scratch_plans`).
- **(3) autonomy 유실 — 수정 완료 (2026-07-25).** 진짜 블로커: `_write_session_files` → `preserve_session_meta_from_prev`가 `autonomy`/`trust_budget`를 보존하지 않아 PATCH L2가 다음 room 턴에서 증발 → outcomes가 L0으로 태깅. `SESSION_META_KEYS`에 추가 후 live turn fill로 L2 n=10 달성.

시작: `eval "$(make -s dogfood-track-env)" && make dev`(또는 `make api`) → 라이브 세션 진행 → 중간 gate는 `make dogfood-live-gates-watch SESSION_ID=<id>`(수집 아님, Question/MCP/execute 자동 처리). 세션 후 수집은 `feedback-report` / `dogfood-progress-record` / `dogfood-track` 별도 실행.

Composer preset 제거(WORKFLOW §8.2 **P2**)는 archive roadmap item이다. 현재 Composer는 이미 topic-only이며 picker를 노출하지 않는다. Wave B/browser acceptance gate는 **accepted** (2026-07-24 live packet).

### 분기 리뷰 묶음 (한 세션에서 일괄 — NORTH-STAR §3.3 분기 행)

① `AGENT_LAB_QUARTER_BUDGET_USD` 실값 + `make f8-cost-report` 정례화 ② §2.5 흡수 매트릭스 재검토 — SSOT [ABSORB-CC-CODEX-2026-07.md](./ABSORB-CC-CODEX-2026-07.md) (CC/Codex 로컬+공식; Wave 0–2 + **ABS-P2-worktree-yaml** shipped; 잔여 **ABS-P2-skills** N7 동결 · **ABS-P2-hooks/workflows** 문서만) ③ §1.4 KPI 리뷰 ④ N5/S2 재평가 ⑤ dogfood-first 만료 검토 (`history.n` ≥ 30) ⑥ ADR rebuild 재평가 (§3.5).

### 동결 — explicit Human OK 없이 착수 금지

N5 전역 bandit · N7/S3 구현(설계만 ✅) · HS6/HS7 · HSIL Tier D 전체 · Gateway · trading core 표면 · `fork_time_minutes` 자동화(N8 잔여, P3).

---

## 2. Historical shipped 확인 대장 (문서보다 앞선 코드; browser acceptance와 별도)

개별 문서에 아직 반영 안 된 historical code evidence. **이 표는 현재 UX/browser acceptance를 닫지 않으며, 문서 상태와 충돌하면 최신 evidence gate를 우선한다.**

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
make feedback-report JSON=1   # harness_attribution 확인 (큐 1) · S1 lift(P0-5)는 닫힘, N4-D3/N1-30 진행용
python scripts/propose_harness.py --mode list   # HS-M5 닫힘 후 추가 후보 관측; HS6은 Human 확인 전 착수 금지
make eval-surface-local       # T0/T1 supersample (evals/results/latest.json)
make f7-dogfood-report        # F7 closed ON — optional revisit metrics
make dogfood-progress         # suite-log 진행도
make dogfood-progress-auto ONLY=X1,X2   # mission + execute→Oracle mock
make dogfood-track            # 게이트 현황 (live ledger)
make dogfood-track-run        # live bootstrap: F7 start + env + next actions
make dogfood-track-env        # live supervisor exports (S1+F7+explore)
make dogfood-live-gates-watch SESSION_ID=<id>  # mid-turn Question/MCP/execute
# optional offline: make dogfood-track-run-mock
```

---

## 4. 문서 정비 백로그 (핵심 문서 피드백 — 별도 정비 PR용, 코드 작업과 분리)

**2026-07-08 전부 ✅ 반영 완료** — NORTH-STAR(D-라벨 정정·§3.1/§3.4 수치 통일·앵커 맵 명령 참조화·N2/N6/N10 이력 §3.3.1 3차 wave 이동), WORKFLOW(P1 TurnContract ✅·§9/§2.5 SSOT 분리 명시), EVAL-PLAN(헤더 현행 가치 명시·"부족한 부분" 재분류), HSIL(§15 HS-M1~M7 개명·§8.4 스키마 복원). 근거는 각 소스 문서에 남음 — 이 문서는 포인터만 유지하므로 상세 이력 없음.

---

## 5. 이 문서의 운영 방법

- **갱신 트리거:** 큐 항목이 닫히거나 시한(⏰)이 지나면 즉시. 최소 주 1회 큐 재정렬.
- **갱신 방법:** 닫힌 항목은 행 삭제 + 소스 문서(NORTH-STAR §3.1 등)에 판정 근거를 남긴다. 이력은 여기 쌓지 않는다 — 이 문서는 항상 짧아야 한다 (~150줄 상한).
- **금지:** 여기서 새 설계·새 ID·새 KPI를 만들지 않는다. 그런 내용이 필요하면 소스 문서를 고치고 여기는 포인터만 갱신.
