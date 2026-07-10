# Liner 연구 6종 검토 및 agent-lab 개선 방향

> **Status:** archived research record · **작성:** 2026-07-08 · **반영 완료:** 2026-07-08
> **Authority:** 없음. 현재 상태·로드맵·착수 판단에 사용하지 않는다. 수용된 결정은 [DESIGN-HARNESS-SELF-IMPROVE.md](./DESIGN-HARNESS-SELF-IMPROVE.md), 현재 상태는 [NOW.md](./NOW.md), 방향은 [NORTH-STAR.md](./NORTH-STAR.md)가 소유한다.
> 본문의 "HSIL DRAFT"와 당시 미구현 표기는 연구 시점 기록으로 보존한다.
> **검토 대상**: `.agent-lab/liner-exports/` — Liner Scholar 프로젝트 [665131](https://scholar.liner.com/ko/projects/665131) 산출물 6종 (문서 2 + 마인드맵 4)
> **기준 문서**: [DESIGN-HARNESS-SELF-IMPROVE.md](./DESIGN-HARNESS-SELF-IMPROVE.md) (HSIL DRAFT) · [NOW.md](./NOW.md) · [NORTH-STAR.md](./NORTH-STAR.md)
> **이 문서의 역할**: ① 자료 6종의 주장 요약·신뢰도 평가 ② 현재 코드/설계와의 사실 대조 ③ HSIL DRAFT에 반영할 수정·추가·기각 목록. 새 1급 개념·새 KPI를 만들지 않는다 — 기존 HS Phase·Tier 어휘에만 매핑한다.

---

## 0. 한 줄 결론

> Liner 연구는 agent-lab의 구조를 **정확히** 읽었고(6계층 스택, evaluator-inside-loop, rule_sync 단방향, HS1-3 미구현 모두 사실과 일치), 지적된 한계의 대부분은 **HSIL DRAFT가 이미 알고 있는 것**이다. 실질 가치는 새 아키텍처 제안이 아니라 **HSIL DRAFT를 APPROVED로 올리기 전에 고쳐야 할 5개 설계 결함**(§4.1)과, 기존 로드맵 항목의 **우선순위·근거 보강**(§4.2)에 있다. 대형 제안(3-에이전트 분리, RL 오케스트레이션, Manager Agent)은 기존 Tier D 동결 판단이 옳았음을 재확인한다(§4.4).

---

## 1. 검토 대상 요약

| # | 자료 | 형식 | 핵심 내용 |
|---|------|------|-----------|
| D1 | HSIL 안전 게이트 한계 전문가 리뷰 (`HSIL 안전 게이트 한계 전문가 리뷰_apa.docx`) | 문서 | 안전 게이트의 **10대 근본 한계**를 3층위(수학적 불가능성 / 구조적 커버리지 갭 / 실무 병목)로 정리 + 5개 권고 |
| D2 | Harness Self-Improvement Loop and Its Stages (`.csv`) | 문서 | **논문 22편**을 HSIL 6단계(ATTRIB~MERGE)별로 선정 근거와 함께 매핑 |
| M1 | agent-lab: Structure, Workflow, References (`liner-mindmap-4332218.md`) | 마인드맵 34노드 | agent-lab 현행 구조(Super Sample T0/T1/T2 · HSIL 6단계 · Editable Surface Tier)를 학술 문헌과 단계별 정합시킨 지도 |
| M2 | 슈퍼샘플 오픈소스 생태계 (`liner-mindmap-4332336.md`) | 마인드맵 34노드 | HSIL 단계별 GitHub 오픈소스 대응물(OpenHands, promptfoo, AEGIS 등) + agent-lab 차별성 분석 |
| M3 | HSIL 재설계 연구 방향 (`liner-mindmap-4332439.md`) | 마인드맵 23노드 | D1의 10대 한계를 극복하는 **7개 재설계 축** (검증 기반 REGRESS, Two-Gate PROPOSE, 회복 중심 거버넌스 등) |
| M4 | 6계층 오케스트레이션 분석 (`liner-mindmap-4332523.md`) | 마인드맵 45노드 | agent-lab 오케스트레이션 스택의 **7개 구조적 한계**와 7개 슈퍼샘플 대조 기반 **7개 개선안** |

자료 간 관계: **M1·M2 = 현황 지도** (agent-lab이 무엇인지) → **D1·D2 = 이론적 한계와 근거 문헌** → **M3·M4 = 개선 제안**. 실질 검토 대상은 M3(HSIL 안전성 축)과 M4(오케스트레이션 축)의 제안 14건이다.

---

## 2. 신뢰도 평가 — 근거를 어디까지 믿을 것인가

### 2.1 사실 관계: agent-lab 서술은 정확하다

M1·M4의 agent-lab 서술을 코드·설계 문서와 대조한 결과 **전부 사실과 일치**:

| Liner 주장 | 검증 결과 |
|-----------|-----------|
| 6계층 스택 (Room→Runtime→Plan/Execute→Mission→Session→API) | HSIL DRAFT §4.1과 동일 |
| feedback_advisor가 평가·진단 겸수 (evaluator-inside-loop) | 사실 — HSIL Tier D가 「Evaluator inside evolution loop = reward hacking」으로 보류 명시 |
| rule_sync 단방향 (SSOT→하네스, 역류 없음) | 사실 — HSIL §4.3 「단방향」 명기 |
| HS1-3 traces 미구현 | 사실 — HS1 로드맵 항목, 플래그 default 0 |
| Human Inbox는 동기 승인/거부만 | 사실 — 비동기 이슈 채널 없음 |
| TurnPolicyEngine 정적 라우팅, s2_role_bandit는 세션 국소 | 사실 — N5 전역 bandit는 동결 중 |
| memory_store consumer 0 · eval_harness call site 0 | 사실 — HSIL §4.2 명기 |

즉 Liner는 저장소 문서를 직접 읽고 매핑했으며, **현황 진단의 신뢰도는 높다.**

### 2.2 근거 문헌: 신뢰도는 이원화해서 취급해야 한다

D2의 22편 + D1 인용 문헌의 상당수가 **2026년 3~4월 preprint, 인용 0**이다. 특히:

- **인용 실적 있음 (설계 근거로 사용 가능)**: ACE (인용 64), Where LLM Agents Fail (21), Evolving Orchestration (38), W4S (9), Spectrum Analysis 실패 귀속 (8), Securing AI Agent Execution (7)
- **인용 0 preprint (방향 신호로만 사용, 정량 수치는 미검증 취급)**: Scrivens 분류기 불가능성 정리(Zenodo — 자체 업로드 저장소, 피어리뷰 없음), "The Last Harness You'll Ever Build", CAAF, Layered Mutability, Reward Hacking as Equilibrium, Claude Code Permission Gate 스트레스 테스트 등
- **실체 확인 불가**: M4의 "RWL (Ralph Wiggum Loop)" — 검증 가능한 출처 없음. "LLM 평가 80회 시험 0% 역설 탐지율"은 CAAF 단일 preprint의 주장

**운영 원칙 제안**: 아래 §4의 모든 채택 항목은 *논문의 정량 수치*(153배 격차, FNR 70.3% 등)가 아니라 *구조적 논증*(분류기와 검증기는 다른 것이다, 롤백 후 메모리에 드리프트가 남는다 등)에만 기대도록 작성했다. 정량 수치를 KPI 목표치로 승격하지 않는다.

### 2.3 제안의 성격: 「이미 아는 것」과 「새로 배울 것」 구분

M3·M4 제안 14건 중:

- **7건은 HSIL DRAFT가 이미 계획/보류 판정한 것과 동일** — traces 구현(HS1-3), evaluator 분리(Human Inbox=outside evaluator + Tier D 보류), held-out 검증(HS4), 부정 결과 보존(HS4-5), Two-Gate 유사 게이트(HS4), preset 진화(HS6), Human 감독 위치(§12)
- **5건은 DRAFT의 실제 빈틈을 찌른다** → §4.1 (P0)
- **2건은 방향 자체를 바꾸는 대형 제안** (RL TurnPolicy, Manager Agent) → §4.4 기각/동결 유지

---

## 3. 지적 사항 ↔ 현재 상태 대조 매트릭스

M4의 7한계 + D1의 10한계를 통합하면 실질적으로 **9개 독립 지적**이다. (겹치는 것 병합)

| # | 지적 (출처) | 사실인가 | 현재 대응 | 빈틈 여부 |
|---|------------|---------|-----------|----------|
| G1 | REGRESS가 분류기(pass/fail) 기반 → 장기적으로 안전 퇴화 또는 효용 붕괴 (D1-1, M3-1) | 구조적 논증은 타당 | Oracle(결정론 검증)이 이미 존재하나 HS4 설계는 pytest/dogfood **통과율** 중심 | **빈틈** → P0-1 |
| G2 | 순환 보정: 수정이 과거 해결된 실패를 재도입 (D1-5 확률적 진동) | 타당 | HS4-2 held-in은 *현재* 패턴의 태그만 검사 — **과거 해결 패턴 누적 셋 없음** | **빈틈** → P0-2 |
| G3 | 롤백해도 ledger/playbook에 드리프트 잔존 (래칫 문제, D1-7) | 타당 | HS5 MERGE에 롤백 명세 없음; playbook bullet에 하네스 버전 provenance 없음 | **빈틈** → P0-3 |
| G4 | 도구 치환: 권한 티어 경계를 다른 표면으로 우회 (D1-4) | 타당 — **agent-lab 구체 사례 발견** (§4.1 P0-4) | frozen prefix + post-merge diff 감사(§14.4)뿐 | **빈틈** → P0-4 |
| G5 | 레드 퀸: 표면 추가 시 평가 커버리지가 상대적으로 감소 (D1-3·8) | 타당 | eval case 동시 확장 의무 없음 (Tier B 오염 방지는 별개 문제) | **빈틈** → P0-5 |
| G6 | 관측 단절: 하위 에이전트(DELEGATE, Oracle) 추적이 상위 미노출 (M4-2.4) | 사실 | HS1-3 traces + HS7-2가 커버 예정 | 계획됨 → P1 근거 보강 |
| G7 | 비동기 Human oversight 부재 (M4-2.6) | 사실 | 없음 — Inbox는 동기 게이트만 | **신규 후보** → P1-2 |
| G8 | evaluator-inside-loop (feedback_advisor 평가·진단 겸수) (M4-2.1) | 사실 | HSIL은 **머지 판정**을 Human Inbox(밖)에 둠 — 진화 루프의 게이트는 이미 밖. advisor의 겸수는 S1(턴 셋업) 국한 | 부분 대응 — 상시 3-에이전트 분리는 기각 (§4.4) |
| G9 | 정적 TurnPolicy / Manager Agent 부재 (M4-2.2·2.7) | 사실이나 **의도된 설계** | N5 동결 + 「Human=매니저」 철학 (HSIL §12) | 동결 유지 (§4.4) |

---

## 4. 개선 방향

### 4.1 P0 — HSIL DRAFT→APPROVED 전에 문서에 반영할 5건

NOW.md 큐 6(「HSIL DRAFT→APPROVED 결정」)의 선행 조건으로 제안한다. 전부 **문서 수정**이며 코드 착수는 해당 HS Phase 때 한다.

#### P0-1. REGRESS 게이트 원칙 명문화: 「분류기는 신호, 검증기가 게이트」 (G1) — ✅ 반영됨 (2026-07-08, HSIL §9 HS4-1·§10.2)

- **문제**: HS4는 pytest/dogfood 통과율(=이진 분류)로 merge를 판정한다. 분류기 게이트는 반복 수정 하에서 (a) 위험 누적 또는 (b) 과보수화 중 하나로 수렴한다는 구조적 논증(Scrivens, CAAF)이 있고, agent-lab 스스로도 「완료=Oracle verified」를 불변 원칙으로 갖고 있으면서 HS4에는 이 원칙이 안 내려가 있다.
- **반영**: HSIL §10.2 모트 표에 원칙 1줄 추가 — *「HS4 REGRESS에서 벤치마크 통과율은 후보 랭킹 신호로만 쓰고, merge 게이트는 결정론적 assertion(pytest 개별 assert, smoke 38 baseline, Oracle verify)으로 판정한다. 통과율 단독으로 merge 불가.」* HS4-1에 "candidate가 건드린 표면에 대응하는 assertion 목록 명시" 요구사항 추가.
- **비용**: 문서 1줄 + HS4 구현 시 설계 반영. 신규 인프라 없음.

#### P0-2. 해결 패턴 누적 셋 — 순환 보정 방지 (G2) — ✅ 반영됨 (2026-07-08, HSIL §9 HS4-2·§10.2)

- **문제**: HS4-2 held-in은 「동일 `primary_tag` topics」만 검사한다. 후보 A가 패턴 X를 고치고, 이후 후보 B가 패턴 Y를 고치면서 X를 재도입해도 B의 held-in(태그 Y)은 이를 못 잡는다. CAAF가 말하는 「검증된 상태 잠금 부재 → 비정박 임의 보행」의 정확한 사례.
- **반영**: HS4에 요구사항 추가 — *「merge된 모든 patch의 `pattern_id`는 `resolved_patterns.jsonl`(가칭, `.agent-lab/harness/`)에 누적하고, 이후 모든 candidate의 held-in은 자신의 태그 + 누적 셋 전체를 포함한다.」* HS5-4 predictions verified와 연결: 재발 시 해당 patch를 회귀 원인으로 자동 귀속(ATTRIB).
- **비용**: JSONL 1개 + held-in 셋 확장. dogfood 시간 증가는 held-in을 태그당 대표 1 topic으로 제한해 통제.

#### P0-3. 롤백 오퍼레이터와 메모리 드리프트 명세 — 회복을 1급 관심사로 (G3) — ✅ 반영됨 (2026-07-08, HSIL §8.2·§8.3·§9 HS5-6/7·§10.2)

- **문제**: HS5 MERGE에 롤백 절차가 없다. 하네스 파일은 git revert로 복원돼도, 그 하네스 버전이 만든 **outcomes.jsonl episode·playbook bullet·SetupHint 편향은 잔존**한다(래칫 문제). Editable Surface Tier는 파일 권한만 다루고, Tallam이 구분한 「존재 권한」(내부 상태가 어떤 속도·검토로 변하는가)은 미설계.
- **반영**: HS5에 작업 2건 추가 —
  1. *HS5-6 (가칭)*: playbook bullet과 failure_pattern episode에 `harness_rev`(생성 당시 manifest/patch 버전) 필드 추가. 이미 §8.2·8.3 스키마가 있으므로 필드 1개씩.
  2. *HS5-7 (가칭)*: `harness_patch` 롤백 시 해당 `harness_rev`로 생성된 playbook bullet을 `status: quarantined`로 전환(삭제 아님 — 부정 결과 보존 원칙 유지). ledger episode는 불변 유지하되 feedback_advisor RECALL에서 quarantined rev 필터.
- **비용**: 스키마 필드 2개 + RECALL 필터 1개. HSIL 문서 백로그(§NOW 4)의 「§8.4 dangling reference 복원」과 같은 PR에서 처리 가능.

#### P0-4. 도구 치환 벡터 봉쇄: hooks.toml은 Tier A일 수 없다 (G4) — ✅ 반영됨 (2026-07-08, HSIL §7·§14.4)

- **문제**: **이번 검토에서 발견된 구체 결함.** HSIL §7.1은 `.agent-lab/hooks.toml`을 Tier A(경량 승인)로 분류하는데, hooks는 **subprocess 실행**이다(`room/hooks.py`). proposer가 Tier A 권한으로 hook 1줄을 추가하면 임의 명령 실행이 가능해져 Tier C frozen(turn_flow, execute, human_inbox…)을 포함한 **모든 표면을 사실상 수정할 수 있다**. Ji et al.의 도구 치환 공격(차단된 경로를 다른 도구로 우회)이 agent-lab 권한 설계 안에 그대로 재현된 형태다. 같은 논리로 `.claude/skills/**`(스킬이 Bash 도구를 갖는 경우)도 실행 표면이다.
- **반영**: HSIL §7 수정 —
  1. `.agent-lab/hooks.toml`을 **Tier A→Tier B**(L1 full gate)로 이동. 근거: 실행 표면은 파일 diff 크기와 무관하게 권한 상승 벡터.
  2. §7 서두에 분류 원칙 명문화: *「편집 결과가 subprocess/도구 실행을 유발하는 표면(hooks, 실행형 skill)은 diff가 아무리 작아도 Tier B 이상. Tier A는 선언적 표면(프롬프트 텍스트, 수치 파라미터, 비실행 스킬 문서)만.」*
  3. §14.4 모트 감사에 항목 추가: *「Tier A patch merge 후 hooks 실행 카탈로그(등록된 명령 목록) diff 없음 확인.」*
- **비용**: 문서 수정만. 자동화 폭이 다소 줄지만(hooks 자동 개선 불가) 안전 원칙상 옳은 트레이드다.

#### P0-5. 평가 표면 동시 확장 규칙 — 레드 퀸 대응 (G5) — ✅ 반영됨 (2026-07-08, HSIL §9 HS3-6·HS4-6)

- **문제**: proposer가 새 표면(preset 파라미터, 프롬프트 블록, 스킬)을 추가할 때 그 표면을 검사하는 eval case는 자동으로 안 생긴다. 표면은 늘고 평가는 그대로면 커버리지는 단조 감소한다 — 이것이 레드 퀸 논증의 실용 번역이다.
- **반영**: HS3 PROPOSE 요구사항 추가 — *「PatchCandidate가 manifest에 새 glob/블록을 추가하거나 신규 플래그를 도입하는 경우, 대응하는 dogfood topic 또는 evals case를 함께 제안하지 않으면 regression_gate가 후보를 거부한다.」* (F2 「신규 feature 플래그는 최소 1개 프로필에 소속」 가드와 동형의 규칙 — 이미 검증된 패턴의 확장이다.)
- **비용**: regression_gate에 검사 1개. eval case 추가 자체는 Tier B이므로 Human gate가 자동 적용된다.

### 4.2 P1 — 기존 로드맵 항목의 보강 (새 Phase 없음)

| # | 항목 | 매핑 | 내용 |
|---|------|------|------|
| P1-1 | **traces 우선순위 유지·강화** | HS1-3 (기존) | G6(관측 단절)은 4개 자료가 공통 지적한 유일한 항목. HS1 착수 시 traces를 선행 작업으로. Forage V2의 append-only 원칙(추적 불변성)을 traces 파일 계약에 명시 — 이미 gitignore 경로라 비용 없음 |
| P1-2 | **비동기 Human 이슈 파일링** | HS5 + `mission/loop.py` (기존 모듈 연결) | Inbox에 `issue`(비차단 방향 조정) 카드 유형 추가 → mission loop가 Discuss↔Execute **자연 전환점**에서 소비. TheBotCompany 패턴이지만 새 개념 불필요 — Inbox SSOT + Mission FSM 연결 1건. HS5 범위에 포함할지 별도 N 이니셔티브로 둘지는 APPROVED 결정 시 판단 |
| P1-3 | **경량 capacity 게이트: 1 candidate = 1 axis** | HS3-4 (기존 trigger 조건 확장) | Two-Gate(VC 상한)의 실용 번역. PatchCandidate가 **복수 축**(프롬프트+preset+hooks 동시)을 건드리면 거부 — 다축 상호작용의 창발적 복잡도 폭발을 원천 차단하고, 회귀 귀속(ATTRIB)도 단순해진다. diff 파일 수·크기 상한도 manifest에 명시 |
| P1-4 | **3단계 인과 귀속 태그** | HS0/HS1 `failure_tags` (기존 스키마 확장) | 즉각원인→근접원인→근원원인 구조(Trajectory-Informed Memory, 인용 실적은 낮으나 Spectrum Analysis 인용 8 계열). `failure_pattern` episode에 `cause_chain` 선택 필드 — 필수화하지 않고 weakness_miner가 채울 수 있을 때만 |
| P1-5 | **proposer 서킷 브레이커** | HS5-5 KPI (기존) + 플래그 런타임 연결 | D6 gate(prediction_accuracy ≥ 0.5)는 승격 조건인데, **운영 중 하락** 시 자동 차단이 없다. 6차원 병목 중 「학습 가능 정보 단조성」의 실용 번역: `prediction_accuracy`가 직전 스냅샷 대비 하락 2회 연속이면 `AGENT_LAB_HARNESS_PROPOSER`를 세션 수준에서 자동 OFF + Inbox 알림. 자동 재활성화 없음(Human만) |

### 4.3 P2 — 조건부 채택 (동결 해제 조건만 명시)

| 항목 | 출처 | 판정 | 해제 조건 |
|------|------|------|-----------|
| Room 합의에 결정론 신호 결합 (UAI-lite) | M4-4.3 | 부분 채택 후보 | LLM 합의 판정에 구조 신호(BLOCK 미해소 수, refs 유효율 — 이미 score-session에 있는 지표)를 곱하는 형태. F7 결정(⏰ 07-12)과 S1 lift 데이터가 쌓인 뒤 별도 설계. **지금 착수 금지** — 큐 1~2와 경합 |
| 교차 세션 turn policy 학습 | M4-4.2 | N5 동결 유지 | `by_source.history.n ≥ 30` (NORTH-STAR 분기 리뷰 조건과 동일) + S1 lift 양수 입증 후. REINFORCE 도입은 그때도 과잉 — bandit 승격이 먼저 |
| 양방향 피드백 (하네스 성과 → 오케스트레이션 정책 역류) | M4-4.5 | 장기 관찰 | HS0 `harness_attribution`이 사실상 이 역류의 최소 단위(성과 측정→리포트). 자동 역류는 evaluator-inside-loop 재도입 위험 — HS5 E2E 1건 + prediction_accuracy 데이터 후 재평가 |

### 4.4 기각 — 채택하지 않는 것과 그 이유

| 제안 | 출처 | 기각 이유 |
|------|------|-----------|
| **Worker/Evaluator/Evolution 3-에이전트 상시 분리** | M4-4.1 | agent-lab의 대응물이 이미 존재: 평가=Oracle(루프 밖 결정론 검증), 최종 게이트=Human Inbox(루프 밖), 제안=offline script(HS3-5). LLM 에이전트 3개를 상시 띄우는 것은 토큰 비용·복잡도 대비 이득 불명이고, adversarial LLM evaluator는 그 자체가 또 하나의 분류기다(G1 논증이 부메랑으로 적용됨). **분리 원칙은 이미 지켜지고 있고, 에이전트 수는 원칙이 아니다** |
| **RL 기반 TurnPolicy (Puppeteer/REINFORCE)** | M4-4.2 | 세션 수 자체가 부족(`history.n < 30`)한 단계에서 RL 정책은 학습 불가. 다목적 보상 설계는 리워드 해킹 표면만 넓힌다. P2로 강등 |
| **Manager Agent (decompose→refine→assign)** | M4-4.7 | HSIL §12 「Human=스택 위」 철학과 정면 충돌. 질문 선택·작업 분해의 가치 판단은 의도적으로 Human 소관. mission loop FSM이 기계적 전환을 이미 담당. 단 P1-2(비동기 이슈 소비)가 이 제안의 유용한 부분집합을 흡수한다 |
| **Lipschitz ball verifier 직접 도입** | M3-1 | 매개변수 공간(LoRA 가중치) 검증 기법 — agent-lab은 가중치를 수정하지 않는다(SIA는 Tier D). 「분류→검증 전환」이라는 **원칙**만 P0-1로 수용하고 기법 자체는 부적용 |
| **조합 capacity 프록시(VC 차원 상한) 정식 구현** | M3-2 | 하네스 편집의 VC 차원을 계산할 방법이 없다(논문 스스로 open problem으로 명시). P1-3의 「1 candidate = 1 axis + diff 상한」이 실용적 등가물 |
| **평가 기준 자율 발견 (Forage V2 Generation 3)** | M1-1.2 | eval surface는 Tier B(Human gate 필수)로 동결된 설계 — 평가 기준을 루프가 스스로 바꾸는 것은 G5(레드 퀸)·Campbell 전이를 스스로 여는 행위 |

---

## 5. NOW.md 반영 제안

실행 큐를 바꾸지 않는다 — 큐 1~3(F7, S1 dogfood, N4)은 그대로가 옳다. 제안은 2건:

1. **큐 6 「HSIL DRAFT→APPROVED 결정」의 닫힘 기준에 추가**: 「§4.1 P0 5건의 반영 여부 판정 포함」. P0-4(hooks.toml Tier 이동)는 문서 수정만으로 즉시 반영 가능하므로 HSIL 문서 정비 백로그 PR(NOW §4 HSIL 행)과 묶는 것을 권장.
2. **동결 목록 확인**: 본 검토는 기존 동결(N5 · HS6/HS7 · Tier D 전체)을 **전부 재확인**했다. Liner 자료를 근거로 동결을 해제할 항목은 없다.

---

## 6. 자료별 상세 평가 (참고)

### D1 — 전문가 리뷰 (10대 한계)

가장 밀도 높은 자료. 3층위 구분(수학적 불가능성 / 구조적 갭 / 실무 병목)이 유용하며, §4의 P0 5건 중 4건이 여기서 나왔다. 다만: ① 근거의 절반이 인용 0 preprint(§2.2), ② 「지수적 정렬 붕괴」(Tětek, 2020)는 RL 자가수정 에이전트 모델 기반이라 하네스 편집 루프에 직접 이식하기엔 가정 차이가 큼 — 서킷 브레이커(P1-5) 수준의 보수적 번역만 채택, ③ 권고 중 「하네스-모델 경계 동적 모델링」은 측정 방법이 없어 실행 불가능한 권고.

### D2 — 22편 논문 매핑

HSIL 단계별 문헌 지도로서 가치가 있다. 특히 REGRESS 계열(TDAD의 P→F flip 게이팅, AgentAssay의 행동 지문, SGM의 오류 예산, AgentDevel의 RC 승격)은 HS4 구현 착수 시 참조 목록으로 유효 — HSIL §3 카탈로그(R0~R23)에 없는 신규 항목들이다. HS4 착수 시 이 4편을 R24~R27로 편입 검토 권장.

### M1·M2 — 현황 지도

정확하나 새 정보는 적다. M2의 오픈소스 목록 중 실용 참조 가치: **promptfoo/DeepEval**(HS4 회귀 인프라 선례), **AEGIS**(사전 실행 방화벽 — P0-4의 hooks 감사 설계 시 참조). M2의 「agent-lab 차별성」 절(6단계 명시 파이프라인 + Tier + T0/T1/T2 통합)은 대외 문서(README/포지셔닝)에 재사용할 만한 서술.

### M3 — 재설계 7축

P0-1·2·3·5와 P1-5의 원천. 7축 중 「REGRESS 매개변수 공간 검증」·「조합 capacity 프록시」는 기각(§4.4), 나머지는 보수적 번역으로 채택.

### M4 — 오케스트레이션 7한계·7개선

현황 진단(7한계)은 전부 사실(§3). 개선안 7개 중 채택 2(traces=P1-1, 비동기 oversight=P1-2), 조건부 2(UAI-lite, 양방향 피드백=P2), 기각 3(3-에이전트 분리, RL TurnPolicy, Manager Agent). 기각 3건이 모두 「에이전트를 늘리고 학습을 넣는」 방향인 것은 우연이 아니다 — Liner의 슈퍼샘플 대조가 학술 시스템(연구 프로토타입) 기준이라, dogfood 데이터 n<30인 운영 시스템의 제약을 반영하지 못한다.

---

## 7. 요약표

| 분류 | 건수 | 항목 |
|------|------|------|
| **P0** (APPROVED 전 문서 반영) | 5 — **전부 ✅ 2026-07-08 반영 완료** | 검증기-게이트 원칙 · 해결 패턴 누적 셋 · 롤백/메모리 드리프트 · hooks.toml Tier B 이동 · 평가 동시 확장 |
| **P1** (기존 HS Phase 보강) | 5 | traces 강화 · 비동기 이슈 파일링 · 1 candidate = 1 axis · 인과 체인 태그 · proposer 서킷 브레이커 |
| **P2** (조건부, 해제 조건 명시) | 3 | UAI-lite 합의 신호 · 교차 세션 policy 학습 · 양방향 피드백 |
| **기각** | 6 | 3-에이전트 상시 분리 · RL TurnPolicy · Manager Agent · Lipschitz verifier · VC 프록시 · 평가 기준 자율 발견 |

가장 중요한 단일 발견: **P0-4 (hooks.toml이 Tier A로 분류된 것은 도구 치환 벡터)** — Liner가 인용한 권한 갭 연구를 agent-lab 설계에 대입했을 때 실제로 성립하는 유일한 즉시 수정 대상이다.
