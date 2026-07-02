# Agent Lab North Star — 슈퍼 샘플 로드맵

> **작성:** 2026-07-02 · **역할:** 중장기 방향성 + 완성도 추적의 canonical 문서
> **관계 문서:** 전략 포지션 상세 → [STRATEGIC-DIRECTION-2026.md](./STRATEGIC-DIRECTION-2026.md) · shipped 여부 → [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md) · 현재 구조 → [FLOW.md](./FLOW.md)
> **Supersedes:** `artifacts/plans/agent-lab-agi-direction.md`, `agent-lab-long-term-direction.md`, `agent-lab-longterm-direction.md` (3개 초안을 이 문서로 통합)

---

## 0. 정체성: Agent Lab은 슈퍼 샘플이 된다

AI 오버뷰 시대의 경쟁력은 "정답 암기"가 아니라 "가치 있는 노하우를 자기 맥락으로 흡수(fork)하는 능력"이다. 이 생태계에서 신뢰와 권위는 **베낄 가치가 있는 원본(슈퍼 샘플)** 에게 돌아간다.

Agent Lab의 정체성 선언:

1. **흡수한다** — Claude Code, Codex, Cursor, Gajae code(GJC), Fugu, Harness 등 최고 샘플들의 패턴을 자기 맥락으로 fork한다 (§2.5 흡수 매트릭스).
2. **고유한 것을 만든다** — 어디에도 없는 것: 다중 에이전트 협업의 **창발(emergence)로 자기발전 루프를 닫는 것**. 개인은 모델 가중치를 못 바꾸므로, 런타임 협업 토폴로지가 우리의 학습 축이다.
3. **통째로 공개한다** — "내 것을 통째로 벗겨가도 좋다." Agent Lab 자체가 남들이 fork하는 원본이 되는 것이 최종 신뢰 획득 경로다 (§2.1 N8 슈퍼 샘플 트랙).

한 줄 요약: **"창발로 자기발전하는, fork 가능한 Trusted Autonomous Mission Platform."**

---

## 1. 장기 방향성 구체화 — 북극성 3층 구조

기존 북극성("협업 창발 → 자기발전")을 3층으로 구체화한다. 각 층은 아래층이 닫혀야 의미가 생긴다.

### Layer 1 — 창발 엔진 (S1 → S2 → S3)

| 단계 | 목표 | 닫힘 판정 기준 (검증 가능해야 함) | 현 위치 |
|---|---|---|---|
| **S1 내부 루프 폐쇄** | Oracle 성공/실패 패턴이 다음 Room 세팅에 자동 반영 | S1 플래그 기본 ON + `make dogfood-feedback-mock`이 CI에서 default→history 전환을 증명 + 실세션 2주 운영 | 코드 완료(A~D+S1.5), **플래그 전부 OFF — 운영상 안 닫힘** |
| **S2 팀 구성 자기조정** | 과제 유형별 최적 역할 조합을 스스로 학습·재사용 | per-agent attribution + ε-greedy가 bandit 수렴 → 특정 카테고리에서 학습된 조합이 default 조합의 clean-pass율을 유의미하게 상회 | 설계만 존재 (~10%) |
| **S3 외부 능력 자가 통합** | Codex/Cursor/CC 스킬·플러그인 + 외부 MCP를 스스로 발견·연결·활용 | Room이 미션 중 "이 도구가 필요하다"고 판단 → plugin_discovery로 탐색 → Human gate 승인 → 다음 턴부터 사용, 전 과정 run.json 기록 | `plugin_discovery.py`, `mcp_tool_contract.py`, `skill_drafts.py` 부품만 존재 (~15%) |

**순서 불변 (재확인):** S3부터 하면 도구만 늘고 창발은 안 생긴다. S1 운영 닫힘 → S2 → S3.

**S3의 구체화** (기존 문서에서 가장 모호했던 부분):
- **S3a 발견:** MCP registry + CC skills 디렉터리 + Codex/Cursor 플러그인 매니페스트를 주기적으로 크롤/인덱싱 (`plugin_discovery` 확장). Wisdom Index에 "도구 카드"로 저장.
- **S3b 연결:** 에이전트가 미션 중 도구 부족을 선언(`[NEED-TOOL:]` 시그널) → 도구 카드 검색 → 후보 제시 → **Human Inbox 승인 필수** (모트 5 유지) → 세션 스코프로 mount.
- **S3c 활용 학습:** 어떤 카테고리 미션에서 어떤 도구가 clean-pass에 기여했는지 S1 outcome 파이프라인에 그대로 태워 기록. 즉 S3는 새 학습 시스템이 아니라 **S1 루프의 입력 차원을 늘리는 것**이다.
- **S3d 자기적용:** Agent Lab이 자기 자신의 개발 미션(dogfood)에서 CC skills를 스스로 골라 쓰는 상태 = S3 완성 판정.

### Layer 2 — 신뢰 사다리 (Autonomy Ladder)

"Human gate 제거"가 아니라 "신뢰도에 비례한 자율도"로 구체화. 모든 새 자율 기능은 이 사다리 위 어디에 있는지 명시해야 한다.

| 레벨 | 이름 | 동작 | 게이트 |
|---|---|---|---|
| L0 | Manual | 모든 결정 인간 승인 | plan + diff 둘 다 인간 |
| L1 | Assisted | LOW risk + Oracle HIGH confidence → 타임아웃 자동 승인 | `auto_approve_gate` + `diff_risk` |
| L2 | Budgeted | trust_budget 내에서 다건 자동 실행, 소진 시 L1로 강등 | `trust_budget` + 예산 리포트 |
| L3 | Autonomous mission | 토픽만 받고 loop가 계획-실행-검증 반복, BLOCK/HIGH risk만 인간 | mission loop + Human Inbox escalation |

**불변:** 어떤 레벨에서도 BLOCK→409와 worktree 격리는 우회 불가. L3에서도 Human Inbox는 "질문 채널"로 항상 열려 있다.

### Layer 3 — 슈퍼 샘플 (공개·포크 가능성)

내부 품질과 별개로 "외부인이 벗겨갈 수 있는가"를 독립 트랙으로 추적한다.

- **재현 가능:** `git clone` → 15분 안에 mock 미션 1개 완주 (quickstart).
- **이해 가능:** 핵심 개념 6개(§2.2)만 알면 아키텍처 전체를 설명할 수 있는 문서 구조.
- **분리 가능:** Oracle 검증, Room 합의, worktree execute를 각각 단독으로 fork할 수 있는 패키지 경계 (구조 리팩토링 wave가 이미 이 방향).
- **증명 가능:** emergence bench·feedback report 결과를 공개 리포트로 재현 — "창발이 실제로 성능을 올린다"는 주장에 숫자가 붙어야 슈퍼 샘플 자격이 생긴다.

### 완성 정의 사다리 (D0~D4) — 이 문서의 % 산정 기준

과거의 반복 실수: "코드가 있으면 완료"로 선언 → 실제로는 플래그 OFF로 죽어 있음. 앞으로 모든 완성도는 이 사다리로 말한다.

| 단계 | 정의 | 대략적 % |
|---|---|---|
| D0 | 개념/설계 문서만 존재 | 0–20% |
| D1 | 코드 존재, 플래그 default OFF | 20–45% |
| D2 | mock 테스트/bench로 동작 검증 | 45–65% |
| D3 | default ON, 실세션 운영 편입 | 65–85% |
| D4 | 운영 지표로 가치 증명 (KPI 달성, 회귀 베이스라인 편입) | 85–100% |

**금지:** D1 상태를 "구현 완료"라고 부르는 것. D3 이상만 "닫혔다(closed)"고 말한다.

---

## 2. 앞으로의 구체적 방향성

### 2.1 이니셔티브 목록 (N1~N9)

| # | 이니셔티브 | 내용 | 층 | 시기 |
|---|---|---|---|---|
| **N1** | **S1 운영 닫힘** | S1 플래그 기본 ON(최소 supervisor preset), `dogfood-feedback-mock` CI 편입, 실세션 2주 운영 후 feedback_report로 lift 확인 | L1 | 지금 |
| **N2** | **프로필 시스템** | 212개 플래그 → `fast`/`balanced`/`thorough`/`autonomous` 4개 프로필 매핑 (`app_config.py`). 개별 override 유지. 신규 플래그는 프로필 소속 선언 없이 추가 금지 | L1 | 지금~2주 |
| **N3** | **Harness topology 데이터화** | Composer preset은 fast/supervisor 2개 유지. `pipeline`·`producer_reviewer`·`consensus`·`adversarial` 패턴은 `topic_router` topology + `role_plan` + capability seed로 표현 (Settings 분업 UI 퇴출) | L1 | shipped |
| **N4** | **Autonomy Ladder 정식화** | L0~L3을 코드 개념으로 승격: 세션마다 현재 레벨이 run.json과 UI에 표시, 레벨 전환 이벤트 기록 | L2 | 2주~1달 |
| **N5** | **S2 팀 자기조정** | per-agent attribution → ε-greedy 위에 bandit 수렴 → agent pool promote/demote. S1.5 탐색·효과측정 인프라 위에서 | L1 | 1달~ |
| **N6** | **Self-patch meta-loop** | Room이 생성한 개선안을 agent-lab 자기 코드베이스에 적용하는 dogfood 루프의 정례화. 대상은 처음엔 화이트리스트(스킬 문서·프롬프트·preset 파라미터)로 제한, 코어 로직은 인간 gate 필수 | L3 | 1달~분기 |
| **N7** | **S3 외부 능력 자가 통합** | §1 Layer 1의 S3a~S3d. 인터페이스(도구 카드 스키마, `[NEED-TOOL:]` 시그널)는 지금 설계, 구현은 S1/S2 닫힌 후 | L3 | 분기 |
| **N8** | **슈퍼 샘플 트랙** | quickstart(15분 mock 미션) → 예제 미션 3종(코드/리서치/리뷰) → emergence bench 공개 리포트 → fork 가이드. Layer 3 판정 기준을 그대로 체크리스트로 | — | 분기 (S1 닫힘과 병행 가능) |
| **N9** | **검증 서비스화** | OpenAI-compat API(`openai_compat.py` 라우터 존재)에 소비자 만들기 + Oracle을 외부 결과 검증 서비스로 노출. "다른 에이전트가 만든 것을 Agent Lab이 검증한다"가 슈퍼 샘플 서사의 핵심 증거 | — | 분기 |

### 2.2 Concepts — 공개 어휘 6개로 고정

슈퍼 샘플의 조건은 "적은 개념으로 전체를 설명 가능"이다. 공개 어휘를 아래 6개로 **동결**하고, 새 기능은 반드시 이 중 하나의 하위 개념으로 편입한다 (새 1급 개념 추가는 이 문서 개정 필요):

| 개념 | 한 줄 정의 | 구현 축 |
|---|---|---|
| **Mission** | 토픽 하나로 시작하는 목표 단위 | mission loop, goal_ledger |
| **Room** | 비대칭 역할 에이전트들의 합의 공간 | room/, topic_router, preset |
| **Plan** | 합의의 산출물이자 실행의 입력 (Human gate 지점) | plan/, execute gate |
| **Worktree** | 실행 격리 — 실패가 main을 오염 못 함 | plan/worktree, merge |
| **Oracle** | 완료 판정 — verified 없이는 완료 없음 | oracle_core, verify/repair |
| **Wisdom** | 세션을 넘는 학습 — 창발의 기억 장치 | wisdom/, feedback_advisor, code-memory MCP |

내부 모듈 96개가 뭐든, 외부에 말할 때는 이 6개로 말한다. (`인프라 5모트`는 이 어휘의 속성: BLOCK→409는 Room의, 격리는 Worktree의, 감사는 Mission의 속성.)

### 2.3 Workflow 설계 — canonical mission lifecycle

모든 기능은 이 단일 루프 위의 위치로 설명돼야 한다. 루프에 없는 기능은 만들지 않는다:

```
토픽 입력
  → [라우팅]   topic_router: 카테고리 판정 → preset/프로필/에이전트 풀 추천 (N2·N3)
  → [회상]     Wisdom/feedback_advisor: 과거 성공 조합 주입 (S1 RECALL)
  → [합의]     Room: 비대칭 역할 토론, objection/BLOCK, 재조합 (emergence P1~P5)
  → [게이트]   Plan 승인 — Autonomy Ladder 레벨에 따라 인간/자동 (N4)
  → [실행]     worktree 격리 execute
  → [검증]     Oracle + repair loop, diff risk
  → [측정]     emergence KPI + turn metrics + cost ledger (S1 MEASURE)
  → [기록]     run.json + outcome → Wisdom (S1 RECORD)
  → 다음 미션은 더 나은 세팅으로 시작 ─── (루프 폐쇄 = S1)
```

- 워크플로 설계 원칙 1: **측정 없는 단계 금지** — 루프의 각 화살표는 run.json 이벤트를 남긴다.
- 원칙 2: **루프를 끊는 기능 금지** — 예: 측정만 하고 회상에 안 쓰이는 KPI(과거 emergence KPI의 `/dev/null` 문제) 재발 방지.
- 원칙 3: 병렬성은 [합의]와 [실행] 내부에만 존재. 루프 자체는 직렬 — 병렬 에이전트 운영의 과거 문제를 반영한 결정.

### 2.4 UX 설계 방향

Mission OS 3-pane IA 유지 위에서:

1. **Autonomy dial을 1급 UI로** — 세션 헤더에 현재 레벨(L0~L3)과 trust_budget 잔량을 상시 표시. "지금 무엇이 자동이고 무엇이 인간 승인인지"가 항상 보여야 신뢰 사다리가 UX가 된다.
2. **Inbox = 유일한 결정 표면** — plan 승인, diff 승인, NEED-TOOL 승인, BLOCK escalation을 전부 Human Inbox 한 곳으로 수렴. 결정 유형이 늘어도 표면은 안 늘린다.
3. **Evidence-first 읽기 경로** — "에이전트가 뭐라 말했나"보다 "무엇이 검증됐나"가 먼저 보이는 화면 (EvidenceTimeline 확장). 창발 KPI(challenge_yield 등)를 세션 요약 카드에 노출해 사용자가 창발을 체감하게.
4. **프로필 우선 온보딩** — 새 세션 = 프로필 4개 중 선택이 전부. 플래그 212개는 고급 설정 뒤로.
5. **부채 상환 우선** — 새 표면 추가 전에 Phase D(상태 관리: RoomChat 26 useState → 훅 4개, SSE handler map, client.ts 분할)를 끝낸다. 125개 컴포넌트에서 더 늘리는 것보다 통합이 먼저.

### 2.5 참고 샘플 흡수 매트릭스

"무엇을 베끼고, 무엇으로 대체하고, 무엇은 안 하는가"를 명시:

| 샘플 | 흡수할 것 | Agent Lab식 대체/차별 |
|---|---|---|
| **Claude Code** | Skills 포맷·progressive disclosure, hooks 체계, plan mode, 메모리 구조 | 스킬을 단일 에이전트가 아닌 **Room 전체의 공유 능력**으로 mount (S3의 기반) |
| **Codex** | 클라우드 백그라운드 태스크, PR-native 산출물, 샌드박스 정책 | 백그라운드 실행을 worktree+Oracle 게이트 뒤에 두기 — 산출물은 "verified PR" |
| **Cursor** | Composer식 인라인 결정 UX, background agent 상태 표시 | 결정 표면은 Inbox로 수렴(§2.4-2), 에이전트별 창이 아닌 미션별 뷰 |
| **Gajae code (GJC)** | 외부 파이프라인 수용 패턴 ([GJC-ENTRY.md](./GJC-ENTRY.md)) — 외부 산출물을 게이트 뒤로 받는 입구 | GJC 입구를 일반화 → N9 "외부 결과 검증 서비스"의 원형 |
| **Fugu** | 단일 API 뒤로 복잡성 은닉(→ openai_compat), 복잡도→모델 자동 선택(→ model_policy) | 재훈련 대신 **Wisdom 런타임 학습**, 무인 큐 대신 **신뢰 사다리** |
| **Harness** | 6팀 패턴(→ preset 6종), 토큰 효율(progressive disclosure) | 패턴을 고정 선택이 아닌 topic_router 자동 추천 + S2 학습 대상으로 |
| 관찰 목록 | OpenHands·SWE-agent(verified 벤치 방법론), LangGraph(그래프 오케스트레이션 API 디자인), Aider(repo-map 접근) | 분기마다 이 표를 갱신 — 새 샘플 발견 시 "흡수/대체/안 함" 판정 후 추가 |

**흡수의 규칙:** 어떤 샘플 패턴도 5모트(BLOCK→409, worktree 격리, Oracle+Repair, run.json 감사, Human Inbox)를 약화시키는 형태로는 흡수하지 않는다.

---

## 3. 현 개발 단계 점검 — 완성도 게이지

기준일 2026-07-02. %는 §1의 D0~D4 사다리 기준. **갱신 규칙: 아래 표를 고칠 때는 반드시 판정 근거(플래그 상태·테스트·운영 기간)를 같이 고친다.**

### 3.1 영역별 게이지

| 영역 | 완성도 | 단계 | 판정 근거 · 부족한 것 |
|---|---|---|---|
| Worktree 격리 + execute gate | **85%** | D4 | 모트. smoke 37 베이스라인 편입. 남은 것: 장기 운영 엣지(충돌 병합 자동화 품질) |
| Oracle 검증 + repair | **80%** | D3~D4 | 모트. 남은 것: live 검증 경제성 상시화, confidence 산출의 일관성 |
| Room 합의 + 창발 파이프라인 (P1~P5) | **65%** | D2 | 코드·mock bench 완료, smoke 편입. **창발 관련 플래그 다수 default OFF → 실세션 창발 증거 없음** |
| S1 피드백 루프 | **55%** | D1~D2 | A~D+S1.5 코드 완료, APPLY→MEASURE 버그 수정, dogfood mock 검증 도구 존재. **전 플래그 OFF = 운영상 안 닫힘.** N1이 최우선인 이유 |
| Preset/프로필 시스템 | **30%** | D1 | preset 2개(fast/supervisor)뿐 — 문서의 6패턴 대비 괴리. 프로필 0개, 플래그 식별자 212개 방치 |
| Trust-gated 자율성 (L1~L2) | **45%** | D1~D2 | auto_approve_gate·trust_budget·diff_risk 부품 존재. 사다리(L0~L3)로 통합된 단일 개념 부재, UI 노출 없음 |
| S2 팀 자기조정 | **10%** | D0 | 설계만. S1.5의 탐색(ε-greedy)·효과측정이 기반 인프라로 준비됨 |
| S3 외부 능력 통합 | **15%** | D0~D1 | plugin_discovery·mcp_tool_contract·skill_drafts 부품 존재, 루프 없음. 인터페이스 설계만 선행(N7) |
| 컨텍스트 품질 (repo_map·compaction) | **50%** | D2 | 구현+self-eval 완료. **실세션 품질 평가 못 해 OFF에 갇힘** — LLM judge 크레딧 문제. F7 참조 |
| 관측·평가 (eval harness·bench·KPI) | **70%** | D3 | 도구 풍부(emergence bench, feedback report, dogfood suite). 남은 것: 지표→의사결정 연결의 정례화 |
| Frontend Mission OS | **60%** | D3 | Phase A~C(모션·접근성·API 계약) 완료. **Phase D 상태 관리 미완** — RoomChat 26 useState, client.ts 2,740줄, 컴포넌트 125개 |
| OpenAI-compat API (N9) | **35%** | D1 | 라우터 존재. 소비자·문서·감사 헤더 등 서사 완성 없음 |
| 슈퍼 샘플 준비도 (Layer 3) | **20%** | D0~D1 | 내부 문서는 풍부하나 외부인용 quickstart·fork 가이드·공개 재현 리포트 없음. 패키징 baseline만 존재 |

### 3.2 구조적 결함 (F1~F7) — %가 아니라 구조가 문제인 것

- **F1. Default-OFF 무덤:** 완성의 정의가 "코드 존재"에 머물러, 창발·S1 등 핵심 기능이 플래그 OFF로 죽어 있다. 측정 없이 쌓인 D1 코드는 자산이 아니라 재고다. → **처방:** D0~D4 사다리 채택(§1), 신규 기능은 "D3 도달 계획" 없이 착수 금지, N1으로 최대 재고(S1)부터 소진.
- **F2. 플래그 스프롤 가속:** 6월 108개 → 현재 식별자 212개. 조합 공간이 평가 능력을 초과했다. → **처방:** N2 프로필 4개, 신규 플래그는 프로필 소속+만료 조건(승격 or 제거 시점) 선언 의무화.
- **F3. 문서-코드 괴리:** 문서의 preset 6패턴 vs 코드 2개처럼, 문서가 코드보다 앞서 있으면 외부인(그리고 미래의 에이전트)이 코드를 신뢰하지 못한다. 슈퍼 샘플에겐 치명적. → **처방:** 격차 항목은 TRACEABILITY에 partial로 명시, 이 문서 게이지가 단일 진실.
- **F4. run_meta 이중 상태 함정:** 턴 종료 시 디스크 run.json에서 dict를 재시작해 in-memory 변경이 유실되는 패턴으로 동종 버그 2회(emergence P3, S1 roles). 구조적 결함이 반복 버그를 만들고 있다. → **처방:** "합의 루프 중 run_meta 영속은 반드시 턴 종료 replay 경유"를 코드 규칙으로 승격(CLAUDE.md), 가능하면 단일 writer로 리팩토링.
- **F5. 인프라/도메인 혼재:** `src/agent_lab/trading_mission/`(+quant)이 코어와 같은 트리에 있어 north-star 작업의 가시성을 해친다. → **처방:** extensions/examples로 격리, plan 문서를 인프라 트랙 전용으로.
- **F6. 프론트 상태 부채:** 26 useState·2,740줄 client.ts 위에 기능을 계속 얹는 중. Autonomy dial 등 N4 UI가 이 위에 못 올라간다. → **처방:** Phase D를 N4보다 먼저.
- **F7. 품질 평가의 mock 편중:** repo_map·compaction이 "실세션 평가 불가"로 OFF에 갇힘 — 평가 수단 부재가 기능 승격의 병목이 된 상태. → **처방:** 본인 실사용 N일 프로토콜을 정식 평가 방법으로 채택(플래그 ON으로 며칠 사용 → 체감+지표 기록 → 승격/제거 판정). 크레딧 확보 시 LLM judge 병행.

### 3.3 실행 순서

| 시기 | 할 일 | 닫힘 판정 |
|---|---|---|
| **지금** | N1 S1 운영 닫힘 (플래그 ON + CI 편입 + 실세션 운영) | feedback_report에서 history 소스 lift 확인 |
| **지금** | F4 규칙 승격 (CLAUDE.md 1줄) + F5 trading 격리 결정 | 규칙 추가 커밋 / plan 문서에서 trading delta 0줄 |
| **~2주** | N2 프로필 4개 + F2 플래그 신규 규칙 | `make list-flags`에 프로필 매핑 출력 |
| **~2주** | N3 preset 6패턴 (F3 해소) | preset 로드 테스트 + topic_router 추천 연결 |
| **~1달** | F6 Phase D → N4 Autonomy Ladder UI | RoomChat useState ≤ 8 · 세션 헤더 레벨 표시 |
| **~1달** | F7 실사용 평가 프로토콜로 repo_map/compaction 승격 판정 | ON 승격 or 제거 (방치 금지) |
| **분기** | N5 S2 → N6 self-patch → N7 S3 인터페이스 → N8 슈퍼 샘플 트랙 → N9 검증 서비스 | 각 항목 D3 도달 |

---

## 4. 이 문서의 운영 방법

- **갱신 트리거:** ① 마일스톤(N1~N9) 하나가 D 단계를 넘을 때 §3.1 게이지 갱신 ② 분기마다 §2.5 샘플 매트릭스 재검토 ③ 새 1급 개념이 필요해지면 §2.2 개정 (신중하게).
- **역할 분담:** 이 문서 = 방향+완성도의 단일 진실 / [STRATEGIC-DIRECTION-2026.md](./STRATEGIC-DIRECTION-2026.md) = 경쟁 분석 배경(이력) / [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md) = 기능 단위 shipped 상태.
- **판정 언어:** "완료"라는 말은 D3 이상에만 쓴다. D1은 "코드 존재", D2는 "mock 검증"이라고 부른다.
- **모트 체크:** 어떤 이니셔티브든 착수 전에 한 문장으로 답한다 — *"이 작업은 5모트 중 무엇을 강화하거나, 최소한 약화시키지 않는가?"*
