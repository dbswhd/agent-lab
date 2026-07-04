# Agent Lab North Star — 슈퍼 샘플 로드맵

> **작성:** 2026-07-02 · **역할:** 중장기 방향성 + 완성도 추적의 canonical 문서
> **관계 문서:** 전략 포지션 상세 → [STRATEGIC-DIRECTION-2026.md](./STRATEGIC-DIRECTION-2026.md) · shipped 여부 → [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md) · 현재 구조 → [FLOW.md](./FLOW.md)
> **실행 SSOT:** [CLEANUP-SSOT-2026-07.md](./CLEANUP-SSOT-2026-07.md) · [CLEANUP-PHASE0-SCOPE-2026-07.md](./CLEANUP-PHASE0-SCOPE-2026-07.md)
> **Supersedes:** `artifacts/plans/agent-lab-agi-direction.md`, `agent-lab-long-term-direction.md`, `agent-lab-longterm-direction.md` (3개 초안을 이 문서로 통합)

### 코드네임 범례 (fork 진입용)

| 계열 | 의미 | 주요 섹션 |
|------|------|-----------|
| **S** | Wisdom 루프 S1·S1.5·S2·S3 | §1 Layer 1 |
| **T** | 슈퍼샘플 **신뢰 층** T0–T2 (Oracle / 재현 / 생태계) | §0.1 |
| **L** | **Autonomy** 신뢰 사다리 L0–L3 (execute 자율도) | §1 Layer 2 |
| **D** | 완성 증거 사다리 D0–D4 · §3.1 **%** 구간 | §1 · §3.1 |
| **W** | Wisdom 내부 W1–W3 | §2.2 |
| **N** | 이니셔티브 N1–N9 | §2.1 |
| **F** | 구조적 결함 F1–F12 | §3.2 · ADR §3.5 |
| **Phase** | 실행 wave 1a·1b·1c | §3.3 |

T(슈퍼샘플 판정)와 L(세션 자율도)는 둘 다 “신뢰”지만 **측정 대상이 다름** — 혼동 금지.

### 코드 앵커 맵 (이 문서만 보고 작업 시작할 때의 진입점 — 코드가 진실)

| 대상 | 경로 / 명령 |
|---|---|
| S1 플래그 trio | `src/agent_lab/s1_flags.py` (env 이름 = 코드 상수와 동일) |
| Outcome ledger (W1) | `.agent-lab/outcomes.jsonl` — **repo root 고정** (`src/.agent-lab/`는 과거 CWD 버그 산물, 생기면 병합 후 삭제) |
| W2 리포트 | `make feedback-report` → `scripts/feedback_report.py` (`JSON=1`로 기계 판독, `ROOT=<path>` 지정 가능) |
| Autonomy Ladder (N4) | `src/agent_lab/autonomy_ladder.py` · API `/api/autonomy` GET/PATCH · demotion inbox `src/agent_lab/autonomy_inbox.py` |
| 프로필 (N2) | `src/agent_lab/run/profile.py` (`PROFILES`·`owns`·`flags`) · `make list-flags` |
| Topology hint (N3) | `src/agent_lab/topic_router.py::_resolve_topology` |
| S1.5 explore | `src/agent_lab/s2_role_bandit.py` (subset 힌트만 — 전역 bandit 아님, §1 S2 재정의) |
| S3 부품 | `src/agent_lab/plugin_discovery.py` · `mcp_tool_contract.py` · `skill_drafts.py` (전부 root 모듈) |
| F7 dogfood | `eval "$(make f7-dogfood-env)"` = `AGENT_LAB_REPO_MAP=1` + `AGENT_LAB_COMPACT_TOOL_OUTPUT=1` · 리포트 `make f7-dogfood-report` |
| F8 비용 | `make f8-cost-report` (`JSON=1` 가능) · ledger `.agent-lab/cost_ledger_quarter.json` · 예산 env `AGENT_LAB_QUARTER_BUDGET_USD` |
| 구조 가드 | `make structure-metrics-check` → `scripts/structure_metrics.py` (`hot_path_py_files` F9 ratchet + `large_tsx_files`; baseline drift 시 fail) |
| 창발 bench | `make emergence-bench` → `scripts/emergence_bench.py` |
| run.json 쓰기 규율 (F4) | `patch_run_meta()`·`stamp_run_meta()` (`src/agent_lab/run/meta.py`) — `run_meta[` subscript 금지, CI `tests/test_run_meta_write_discipline.py` |
| 회귀 베이스라인 | `make test-fast` (~2130 mock) · `python scripts/smoke_room.py` (37 baselines) · `make dogfood-suite-mock` |

---

## 0. 정체성: Agent Lab은 슈퍼 샘플이 된다

AI 오버뷰 시대의 경쟁력은 "정답 암기"가 아니라 "가치 있는 노하우를 자기 맥락으로 흡수(fork)하는 능력"이다. 이 생태계에서 신뢰와 권위는 **베낄 가치가 있는 원본(슈퍼 샘플)** 에게 돌아간다.

Agent Lab의 정체성 선언:

1. **흡수한다** — Claude Code, Codex, Cursor, Gajae code(GJC), Fugu, Harness 등 최고 샘플들의 패턴을 자기 맥락으로 fork한다 (§2.5 흡수 매트릭스).
2. **고유한 것을 만든다** — 어디에도 없는 것: 다중 에이전트 협업의 **창발(emergence)로 자기발전 루프를 닫는 것**. 개인은 모델 가중치를 못 바꾸므로, 런타임 협업 토폴로지가 우리의 학습 축이다.
3. **통째로 공개한다** — "내 것을 통째로 벗겨가도 좋다." Agent Lab 자체가 남들이 fork하는 원본이 되는 것이 최종 신뢰 획득 경로다 (§2.1 N8 슈퍼 샘플 트랙).

한 줄 요약: **"창발로 자기발전하는, fork 가능한 Trusted Autonomous Mission Platform."**

### 0.1 신뢰 층 (슈퍼 샘플 판정용)

“Trusted”는 한 가지가 아니다. 측정·판정을 분리한다.

| 층 | 의미 | 측정 / 판정 |
|----|------|-------------|
| **T0 실행 신뢰** | 결과가 Oracle로 deterministic 검증됨 | `run.json` Oracle pass · CI mock |
| **T1 재현 신뢰** | 타인이 로컬에서 동일 플로우 재현 | Layer 3 quickstart · `fork_time_minutes` |
| **T2 생태계 신뢰** | 타인이 fork 후 이슈·PR을 낸다 | fork 수 · 외부 PR (N8 이후) |

T2는 오픈소스 생태계 없이는 달성 불가 — N8 “슈퍼 샘플” 판정에 T1+T2를 명시한다.

---

## 1. 장기 방향성 구체화 — 북극성 3층 구조

기존 북극성("협업 창발 → 자기발전")을 3층으로 구체화한다. 각 층은 **일부 판정**에서 아래층에 의존한다 (예: S2 episode 힌트는 S1 RECORD). 실행은 N8·L1 등 **병행** 가능 — “아래층 100% 닫힘 전에 위층 착수 금지”가 아님.

### Layer 1 — 창발 엔진 (S1 → S2 → S3)

| 단계 | 목표 | 닫힘 / 관측 기준 (검증 가능해야 함) | 현 위치 |
|---|---|---|---|
| **S1 내부 루프 폐쇄** | Oracle 성공/실패 패턴이 다음 Room 세팅에 자동 반영 | **dogfood-active** (supervisor implicit ON). Lift·sample은 §1.4 KPI / `make feedback-report`. Formal D3 닫힘 의식 **없음** (만료: §1 dogfood-first) | **D3(supervisor)** · D1(global) — 코드 A~D+S1.5 |
| **S1.5 세션 로컬 explore** | 같은 미션/세션 맥락에서 ε-greedy 탐색 (Human 가시) | explore 턴이 run.json에 기록, Human override 가능 | D1 — `s2_role_bandit` subset 힌트만 |
| **S2 episode roster 힌트** | 누적 episode에서 history lift 관측 시 advisor 힌트 강화 — **정적 과제분류 bandit 아님** | `MIN_SAMPLE`(기본 3) 이상 episode에서 `clean_pass_delta` > 0 지속 관측 | D0 — N5 **동결** |
| **S3 외부 능력 자가 통합** | Codex/Cursor/CC 스킬·플러그인 + 외부 MCP를 스스로 발견·연결·활용 | Room이 미션 중 "이 도구가 필요하다"고 판단 → plugin_discovery로 탐색 → Human gate 승인 → 다음 턴부터 사용, 전 과정 run.json 기록 | `plugin_discovery.py`, `mcp_tool_contract.py`, `skill_drafts.py` 부품만 존재 (~15%) |

**S2 재정의 (2026-07):** “과제 유형별 최적 역할 조합을 bandit이 학습·재사용”은 **목표에서 제외**한다.

- `topic_router` / `task_type` 카테고리는 **라우팅 힌트**일 뿐, ML 라벨 공간이 아니다. Quant 초기 과제 분류와 같은 **정적·희소** taxonomy로는 수렴할 데이터가 없다.
- S2가 할 일: `outcomes.jsonl` / W2 패턴에서 충분한 sample이 쌓인 **episode 키**(미션·에이전트 subset·결과)에 대해 history vs default lift가 관측될 때만 힌트를 강화한다. 전역 “유형→최적팀” 테이블 학습은 하지 않는다.
- “동적”은 **세션·미션 맥락 + 누적 episode**이지, 사전 정의된 과제 유형 수백 개 분류가 아니다.

**S1 플래그 ON 순서** (`s1_flags.py` — env 이름은 코드와 동일해야 함; supervisor는 trio **implicit ON**):

1. `AGENT_LAB_TURN_METRICS` — MEASURE → `run.json` turn metrics
2. `AGENT_LAB_OUTCOME_LEDGER` — RECORD → `outcomes.jsonl` (의존: 1)
3. `AGENT_LAB_FEEDBACK_ADVISOR` — RECALL/APPLY hint (의존: 1+2; `runtime_flags.py` 주석과 동일)

명시 ON: env `=1` · OFF: `=0` (explicit OFF가 supervisor default보다 우선). 사전 조건: CI `make dogfood-feedback-mock`으로 history 소스 전환 재현.

**S1 관측 절차 (사전 지식 불필요 — 이대로 실행):**
1. supervisor preset으로 실미션 1개 수행 (trio는 implicit ON — 별도 env 불필요).
2. 종료 후 repo root `.agent-lab/outcomes.jsonl`에 episode 줄이 **추가**됐는지 확인 (안 늘었으면 ledger 경로 버그 — 코드 앵커 맵 참조).
3. `make feedback-report JSON=1` 실행 → `by_source.history.n` (≥ `MIN_SAMPLE`=3이면 표본 충족)과 `advisor_lift.history_vs_default` (>0이면 lift 존재) 판독.
4. 수치를 §3.3 "지금" 행의 닫힘 판정 근거로 기록 (커밋 메시지 or CLEANUP-SSOT).

**순서 불변 (재확인):** S3부터 하면 도구만 늘고 창발은 안 생긴다. S1 dogfood → (선택) S1.5 explore → S2 episode 힌트 → S3.

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

**레벨 전환 — 코드화 현황 (2026-07-04):** ladder SSOT·헤더 dial·Human ceiling PATCH·demotion inbox는 shipped (`autonomy_ladder.py`·`autonomy_inbox.py`, N4 v1/v2). **승격 3행은 미코드화** — 코드화 시 트리거 입력은 전부 `run.json` 기존 필드(diff_risk·oracle confidence·trust_budget)에서 취득하고, 전환 이벤트는 ladder audit trail에 기록한다.

| 전환 | 트리거 | 게이트 | 코드화 |
|------|--------|--------|--------|
| L0→L1 | `diff_risk` LOW + Oracle conf ≥ 0.85 **연속 5회** | `run.json` 자동 판정 | ⬜ 미착수 |
| L1→L2 | trust_budget 미소진으로 미션 10개 완주 | Human 수동 승인 | ⬜ 미착수 |
| L2→L3 | 미션 루프 완주율 ≥ 90%, Human escalation ≤ 5% | 분기 Human 리뷰 | ⬜ 미착수 |
| **강등** | Oracle fail **연속 3회** 또는 `diff_risk` HIGH | 즉시 자동 → L0 | ✅ demotion inbox (T-A0) |
| **예산 강등 (F8)** | 분기 `cost_ledger` 예산 상한 초과 (`AGENT_LAB_QUARTER_BUDGET_USD`) | 자동 → L0 | ✅ `cost_ledger_quarter.py` |

### Layer 3 — 슈퍼 샘플 (공개·포크 가능성)

내부 품질과 별개로 "외부인이 벗겨갈 수 있는가"를 독립 트랙으로 추적한다.

- **재현 가능:** `git clone` → 15분 안에 mock 미션 1개 완주. **산출물 = `docs/QUICKSTART.md` (미존재 — N8/P2에서 작성).** 내용 후보: `make install` → `AGENT_LAB_MOCK_AGENTS=1` 세팅 → `python scripts/smoke_room.py` 또는 `make dogfood-suite-mock` 1개 topic — 작성 시 실제 clean clone에서 시간을 재서(`fork_time_minutes`) 확정한다.
- **이해 가능:** 핵심 개념 6개(§2.2)만 알면 아키텍처 전체를 설명할 수 있는 문서 구조.
- **분리 가능:** Oracle 검증, Room 합의, worktree execute를 각각 단독으로 fork할 수 있는 패키지 경계 — **선행: ADR §3.5 Stage 2 (`agent_lab.core` 추출·순환 절단)**. F12가 남아 있는 동안은 분리 fork 불가.
- **증명 가능:** emergence bench·feedback report 결과를 공개 리포트로 재현 — "창발이 실제로 성능을 올린다"는 주장에 숫자가 붙어야 슈퍼 샘플 자격이 생긴다. **선행:** 재현 가능 벤치 프로토콜 SSOT (`make emergence-bench` → `scripts/emergence_bench.py` — 시드·topic 세트·판정 기준을 문서화해 타인이 같은 숫자를 얻어야 함) — 내부 bench 수치만으로는 Layer 3 판정 불가 (N8).

### 완성 정의 사다리 (D0~D4) — 이 문서의 % 산정 기준

과거의 반복 실수: "코드가 있으면 완료"로 선언 → 실제로는 플래그 OFF로 죽어 있음. 앞으로 모든 완성도는 이 사다리로 말한다.

| 단계 | 정의 | 대략적 % |
|---|---|---|
| D0 | 개념/설계 문서만 존재 | 0–20% |
| D1 | 코드 존재, 플래그 default OFF | 20–45% |
| D2 | mock 테스트/bench로 동작 검증 | 45–65% |
| D3 | default ON, 실세션 운영 편입 (dogfood-first — formal closure 의식 **선택**) | 65–85% |
| D4 | 운영 지표로 가치 증명 (KPI 달성, 회귀 베이스라인 편입) | 85–100% |

**판정 책임:**

| 전환 | 판정 방법 | 판정자 |
|------|-----------|--------|
| D1→D2 | `make test-fast` + mock bench | CI |
| D2→D3 | 실세션 dogfood + 플래그 ON 커밋 | Human |
| D3→D4 | §1.4 KPI 목표치 달성 | Human (분기 리뷰) |

**금지:** D1 상태를 "구현 완료"라고 부르는 것. D3 이상만 "닫혔다(closed)"고 말한다.

**스코프 병기:** D 라벨은 **전역 default ON** 기준. preset/기능별만 ON이면 `D3(supervisor)` / `D1(global)`처럼 표기.

**dogfood-first 예외 (2026-07):** N1 등에 D3 **의식적 닫힘** 강제 안 함. **만료:** §3.3 **분기** 행 — `by_source.history.n` ≥ 30 episode 관측 후 formal closure **재검토** (merge gate 아님). 만료 전까지 F1 “Default-OFF 무덤” 예외는 S1 supervisor 스코프에 한정.

### 1.4 KPI Lexicon

**측정 없는 주장 금지** — 아래 KPI는 관측·분기 리뷰용 (dogfood-first 기간 merge gate 아님). §3.1 **%**는 KPI가 아니라 D 구간 표기(§3.1 머리 참조).

| KPI | 정의 | 소스 / 메트릭 | 활성 |
|-----|------|----------------|------|
| `history_match_rate` | advisor `source=history` 힌트와 clean-pass episode subset 일치 비율 | `feedback_report` · `by_source.history` | **now** |
| `feedback_loop_latency` | RECORD→RECALL→APPLY 한 사이클 평균 턴 수 | `run.json` turn index delta | **now** (manual) |
| `clean_pass_delta` | history vs default clean-pass율 차 | `advisor_lift.history_vs_default` | **now** |
| `escalation_rate_by_level` | L0~L3별 Human Inbox 도달률 | inbox · mission tick | **N4 이후** (L 미코드화) |
| `trust_budget_burn_rate` | 기간당 trust_budget 소진 | `run.json` · ledger | partial |
| `fork_time_minutes` | clone → mock 완주 | quickstart (N8) | **N8** |
| `concept_coverage` | 6개 어휘로 설명 가능 shipped 기능 비율 | §2.2 + 분기 Human | aspirational |
| `cost_ledger_quarter` | 분기 LLM·Room 비용 | `cost_ledger.py` · F8 | **F8** |

**판독 명령:** S1 계열 3종은 `make feedback-report JSON=1` 출력의 `by_source.*`·`advisor_lift.*` 필드에서, 비용은 `make f8-cost-report JSON=1`에서 읽는다. `fork_time_minutes`는 clean clone에서 QUICKSTART 완주 시간을 수동 측정.

**N1 관측 (formal closure 아님):** `clean_pass_delta` > 0 이고 `by_source.history.n` ≥ `MIN_SAMPLE`인 episode가 dogfood 중 **지속 관측**되면 S1 루프가 살아 있다고 본다. D4·분기 리뷰 참고치 (aspirational): `clean_pass_delta` ≥ 5pp, `history_match_rate` ≥ 60% when n≥10.

---

## 2. 앞으로의 구체적 방향성

### 2.1 이니셔티브 목록 (N1~N9)

| # | 이니셔티브 | 내용 | 층 | 시기 |
|---|---|---|---|---|
| **N1** | **S1 dogfood-active** | supervisor implicit ON, `dogfood-feedback-mock` CI, 실사용 중 `make feedback-report`로 lift·sample **관측** (§1.4). Formal D3 닫힘 의식 없음 | L1 | 지금 |
| **N2** | **프로필 시스템** | 전체 플래그(`make list-flags`) → `fast`/`balanced`/`thorough`/`autonomous` 4개 프로필 매핑 (`run/profile.py`). 개별 override 유지. 신규 feature 플래그는 프로필 소속 권장 (`make list-flags --profile`) | L1 | ✅ v1 |
| **N3** | **Harness topology 데이터화** | **room_preset** 2개(fast/supervisor) 유지. Topology hint **3종** — `topic_router._resolve_topology`: `parallel` · `producer_reviewer` · `pipeline` ([ROLE-ORCHESTRATION-PLAN.md](./ROLE-ORCHESTRATION-PLAN.md)). **consensus rounds·adversarial**는 LC-L4 `adversarial_gate`·debate — topology hint **아님** | L1 | **partial shipped** (topology 3/3) |
| **N4** | **Autonomy Ladder 정식화** | v1/v2 ✅ (`autonomy_ladder.py` · `/api/autonomy` · dial · demotion inbox). **잔여:** ① 승격 트리거 3종 코드화 (§1 Layer 2 표 ⬜ 행 — 입력은 run.json 기존 필드) ② `escalation_rate_by_level` KPI 산출을 `feedback_report`에 추가 | L2 | 잔여 2건 |
| **N5** | **S2 episode 힌트 (구 팀 bandit)** | [선행: S1 dogfood, S1.5 D2+] episode lift 관측 시 roster 힌트 — **전역 과제분류 bandit 없음**. **동결** until W2 sample 충분 | L1 | 분기 재평가 |
| **N6** | **Self-patch meta-loop** | Room이 생성한 개선안을 agent-lab 자기 코드베이스에 적용하는 dogfood 루프의 정례화. **착수 시 첫 커밋 = 화이트리스트 파일** (`.agent-lab/self_patch_allowlist.txt` — 초기값: `.claude/skills/**`·프롬프트·preset 파라미터만). 코어 로직(`src/agent_lab/**`)은 인간 gate 필수 | L3 | 1달~분기 |
| **N7** | **S3 외부 능력 자가 통합** | §1 Layer 1의 S3a~S3d. **지금 할 것 = 설계 문서 1개:** `docs/S3-TOOL-CARD-SPEC.md` — 도구 카드 스키마(JSON: id·source·capabilities·mount 방법) + `[NEED-TOOL:]` 시그널 문법 + Human Inbox 승인 flow. 구현은 S1/S2 닫힌 후 (부품: 코드 앵커 맵 S3 행) | L3 | 분기 |
| **N8** | **슈퍼 샘플 트랙** | [선행: emergence-bench 프로토콜] ① `docs/QUICKSTART.md` (15분 mock 미션 — §1 Layer 3 "재현 가능" 내용 후보) ② 예제 미션 3종 (`sessions/_regression/` 스타일 fixture) ③ 공개 재현 리포트 (bench 시드·판정 포함) ④ fork 가이드. T1+T2 (§0.1) | — | 분기 |
| **N9** | **검증 서비스화** | 라우터 = `app/server/routers/openai_compat.py` (존재). **잔여:** ① 소비자 1개 (GJC 또는 외부 에이전트가 이 API로 미션 제출) ② Oracle 검증 결과를 응답 헤더/필드로 노출 ③ API 문서. "다른 에이전트가 만든 것을 Agent Lab이 검증한다"가 슈퍼 샘플 서사의 핵심 증거 | — | 분기 |

### 2.2 Concepts — 공개 어휘 6개로 고정

슈퍼 샘플의 조건은 "적은 개념으로 전체를 설명 가능"이다. 공개 어휘를 아래 6개로 **동결**하고, 새 기능은 반드시 이 중 하나의 하위 개념으로 편입한다 (새 1급 개념 추가는 이 문서 개정 필요):

| 개념 | 한 줄 정의 | 구현 축 |
|---|---|---|
| **Mission** | 토픽 하나로 시작하는 목표 단위 | mission loop, goal_ledger |
| **Room** | 비대칭 역할 에이전트들의 합의 공간 | room/, topic_router, room_preset (fast/supervisor) |
| **Plan** | 합의의 산출물이자 실행의 입력 (Human gate 지점) | plan/, execute gate |
| **Worktree** | 실행 격리 — 실패가 main을 오염 못 함 | plan/worktree, merge |
| **Oracle** | 완료 판정 — verified 없이는 완료 없음 | oracle_core, verify/repair |
| **Wisdom** | 세션을 넘는 학습 — 창발의 기억 장치 | wisdom/, feedback_advisor, code-memory MCP |

**Wisdom 내부 3계층** (외부 어휘는 “Wisdom” 하나):

| 계층 | 내용 | 모듈 |
|------|------|------|
| **W1 Episode** | 단일 세션 outcome | `run.json`, outcomes ledger |
| **W2 Pattern** | episode 통계·lift | `feedback_advisor`, `feedback_report` |
| **W3 Memory** | 다음 세션 컨텍스트 | code-memory MCP, `wisdom/` |

S1 루프 = W1 RECORD → W2 RECALL → (optional) W3 / APPLY.

내부 모듈 96개가 뭐든, 외부에 말할 때는 이 6개로 말한다. (`인프라 5모트`는 이 어휘의 속성: BLOCK→409는 Room의, 격리는 Worktree의, 감사는 Mission의 속성.)

### 2.3 Workflow 설계 — canonical mission lifecycle

모든 기능은 이 단일 루프 위의 위치로 설명돼야 한다. 루프에 없는 기능은 만들지 않는다:

```
토픽 입력
  → [라우팅]   topic_router: 카테고리·topology hint → room_preset + role_plan (N2·N3)
  → [회상]     Wisdom/feedback_advisor: 과거 성공 조합 주입 (S1 RECALL)
  → [합의]     Room: 비대칭 역할 토론, objection/BLOCK, 재조합 (emergence P1~P5)
  → [게이트]   Plan 승인 — Autonomy Ladder 레벨에 따라 인간/자동 (N4)
  → [실행]     worktree 격리 execute
  → [검증]     Oracle + repair loop, diff risk
  → [측정]     emergence KPI + turn metrics + cost ledger (S1 MEASURE)
  → [기록]     run.json + outcome → Wisdom (S1 RECORD)
  → 다음 미션은 더 나은 세팅으로 시작 ─── (루프 폐쇄 = S1)
```

- 워크플로 설계 원칙 1: **측정 없는 단계 금지** — 루프의 각 화살표는 run.json 이벤트를 남긴다. KPI 정의는 §1.4.
- 원칙 2: **루프를 끊는 기능 금지** — 예: 측정만 하고 회상에 안 쓰이는 KPI(과거 emergence KPI의 `/dev/null` 문제) 재발 방지.
- 원칙 3: 병렬성은 [합의]와 [실행] 내부에만 존재. 루프 자체는 직렬 — 병렬 에이전트 운영의 과거 문제를 반영한 결정.
- 원칙 4: **run.json 스키마 안정** — 하위 호환 또는 마이그레이션 동반. `patch_run_meta()` 외 직접 쓰기는 F4 allowlist + `tests/test_run_meta_write_discipline.py` CI guard.

### 2.4 UX 설계 방향

Mission OS 3-pane IA 유지 위에서:

1. **Autonomy dial을 1급 UI로** — 세션 헤더에 현재 레벨(L0~L3)과 trust_budget 잔량을 상시 표시. "지금 무엇이 자동이고 무엇이 인간 승인인지"가 항상 보여야 신뢰 사다리가 UX가 된다.
2. **Inbox = 유일한 결정 표면** — plan 승인, diff 승인, NEED-TOOL 승인, BLOCK escalation을 전부 Human Inbox 한 곳으로 수렴. 결정 유형이 늘어도 표면은 안 늘린다.
3. **Evidence-first 읽기 경로** — "에이전트가 뭐라 말했나"보다 "무엇이 검증됐나"가 먼저 보이는 화면 (EvidenceTimeline 확장). 창발 KPI(challenge_yield 등)를 세션 요약 카드에 노출해 사용자가 창발을 체감하게.
4. **프로필 우선 온보딩** — 새 세션 = 프로필 4개 중 선택이 전부. 개별 플래그(`make list-flags`)는 고급 설정 뒤로.
5. **부채 상환 우선** — Phase D(훅 4개 추출 + client 분할)는 ✅ (F6). **다음 부채 = F9:** RoomChat 본체(실측 3497줄·useState 30)의 뷰/상태 분리 — 새 UI 표면 추가 전에 F9 LOC 하강이 관측돼야 한다. 판정: `make structure-metrics-check`의 large_tsx baseline.

### 2.5 참고 샘플 흡수 매트릭스

"무엇을 베끼고, 무엇으로 대체하고, 무엇은 안 하는가"를 명시. **2026-07:** Worktree·Mission UX·review downstream 샘플 추가.

| 샘플 | 흡수할 것 | Agent Lab식 대체/차별 |
|---|---|---|
| **Claude Code** | Skills·hooks·plan mode·메모리; [worktrees](https://code.claude.com/docs/en/worktrees): `--worktree`, `.worktreeinclude`, `WorktreeCreate`/`WorktreeRemove` hooks, subagent `isolation: worktree` | 스킬 = Room 공유 능력(S3); worktree lifecycle → `.agent-lab/worktree.yaml` + MB-6 hooks; **Oracle·execute gate는 유지** |
| **Codex** | 백그라운드 태스크, PR-native, 샌드박스·approvals; [worktrees + Handoff](https://developers.openai.com/codex/app/worktrees) (Local ↔ worktree thread 이동) | 산출물 = verified PR; Handoff → Human IDE 마무리용 branch/thread export (N9/GJC) |
| **Conductor** | [workspace = worktree + branch + diff + checks + PR + archive](https://www.conductor.build/docs/concepts/workspaces-and-branches); setup script, `.context` handoff, merge conflict resolve | execute core **shipped** (PI·CON-diff·MB-6); 남은 것 = **workspace 카드 UX** (`PlanExecutePanel`·Checks·archive 한 surface) |
| **Cursor** | Composer 인라인 결정, background agent 상태, multi-agent worktree (2.0+) | 결정 = Inbox 수렴(§2.4-2); 미션별 뷰 |
| **Claude Squad** | [OSS](https://github.com/smtg-ai/claude-squad) tmux + worktree + TUI; parallel agent pause/review before push | web Mission OS 또는 dogfood ops TUI; AGPL — **패턴만**, 코드 복붙 금지 |
| **Gajae code (GJC)** | 외부 파이프라인 수용 ([GJC-ENTRY.md](./GJC-ENTRY.md)) | N9 "외부 결과 검증" 입구 |
| **Fugu** | 단일 API 뒤로 복잡성 은닉(→ openai_compat), 복잡도→모델 자동 선택(→ model_policy) | 재훈련 대신 **Wisdom 런타임 학습**, 무인 큐 대신 **신뢰 사다리** |
| **Harness** | 6팀 협업 패턴, progressive disclosure | topology hint + role_plan (`topic_router`) — Composer preset 6버튼 **아님** (§1 S2 재정의) |
| **Factory Missions** | [Plan → Mission Control](https://docs.factory.ai/cli/features/missions); milestone validation worker; Human = PM | Room supervisor + `plan.md` + execute gate; **Evidence-first 미션 보드** |
| **Devin** | [Interactive Planning](https://docs.devin.ai/work-with-devin/interactive-planning): citation deep-link, "Wait for approval", `/plan` `/test` `/review`; PR review loop | Plan gate + Scribe; citation → `plan.md` 앵커; Auto-merge **없음** |
| **Graphite** | [Stacked PRs](https://graphite.com/), stack-aware merge queue, PR page AI chat + line fix | plan action N개 → **stacked execute**; Oracle pass 후 merge 순서 |
| **Jules** | Async plan→execute→PR; issue label trigger; mid-flight steer | **N7/GJC 참고만** — core는 sync Room; Human gate 없는 async merge 흡수 금지 |
| **OpenHands** | [Workspace abstraction](https://docs.openhands.dev/sdk/guides/agent-server/overview) (local/Docker/remote); event replay; opt-in sandbox | worktree 1차; `SANDBOX_RUNTIME=docker` 2차 (F5/F8 이후) |
| **Amp** | `AGENT.md`, subagent·thread fork/compact, automation [parallel worktree](https://github.com/sourcegraph/amp-examples-and-guides) | Room shared context; single-thread oracle ≠ Room Oracle |
| **Hermes Agent** (Nous Research, 2026-02) | [Kanban 멀티에이전트](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban): durable queue+state machine(SQLite WAL) — `tasks→task_links→task_comments→task_runs→task_events`; dispatcher `BEGIN IMMEDIATE` 원자적 claim, TTL/PID 기반 stale 재큐잉; `kanban_complete`/`kanban_block` 구조화 핸드오프(침묵 종료=프로토콜 위반); self-improving skill loop + FTS5 cross-session recall | **오케스트레이션 코어 재구축 참조** — `run_meta` god-object(F11) 대체 모델. Hermes에 없는 것(Oracle·worktree·BLOCK→409·Human Inbox)은 Agent Lab 차별점으로 유지 |
| **Mixture-of-Agents** ([Together AI](https://docs.together.ai/docs/mixture-of-agents), arXiv:2406.04692) | Proposer 다수 병렬 응답 → aggregator 종합, 레이어 반복(무상태, fine-tune 불필요) | `topic_router` **parallel** topology 내부 옵션으로 한정 흡수(순수 품질 상승 실험) — objection/BLOCK 게이트 없는 구조라 Room 합의를 **대체 불가**; 게이트 우회 형태 흡수 금지 |
| **관찰 목록** | OpenHands·SWE-agent(verified bench), LangGraph(orchestration API), Aider(repo-map) | 분기 §3.3 **분기** 행에서 이 표 전면 재검토 |

**흡수의 규칙:** 어떤 샘플 패턴도 5모트(BLOCK→409, worktree 격리, Oracle+Repair, run.json 감사, Human Inbox)를 약화시키는 형태로는 흡수하지 않는다.

**흡수 금지 (명시):** Human gate 없이 PR auto-merge(Jules/Devin Auto-Fix 그대로), fire-and-forget multi-day mission(Factory식 inbox bypass), main checkout에서 무 gate sandbox(OpenHands default를 core에 그대로), 게이트 없는 MoA proposer-aggregator로 Room 합의(objection/BLOCK) 전체를 대체.

---

## 3. 현 개발 단계 점검 — 완성도 게이지

기준일 2026-07-02. **§3.1의 %는 KPI 측정치가 아니라 §1 D0~D4 사다리의 구간 표기** (예: 55% ≈ D2–D3 경계). KPI는 §1.4. **갱신 규칙:** 표 수정 시 판정 근거(플래그·테스트·운영) 동반.

### 3.1 영역별 게이지

| 영역 | 완성도 | 단계 | 판정 근거 · 부족한 것 |
|---|---|---|---|
| Worktree 격리 + execute gate | **85%** | D4 | 모트. smoke 37 베이스라인 편입. 남은 것: 장기 운영 엣지(충돌 병합 자동화 품질) |
| Oracle 검증 + repair | **80%** | D3~D4 | 모트. 남은 것: live 검증 경제성 상시화, confidence 산출의 일관성 |
| Room 합의 + 창발 파이프라인 (P1~P5) | **65%** | D2 | 코드·mock bench 완료, smoke 편입. **창발 관련 플래그 다수 default OFF → 실세션 창발 증거 없음** |
| S1 피드백 루프 | **55%** | D3(supervisor) / D1(global) | supervisor trio implicit ON (`s1_flags.py`). lift: §1.4 · `make feedback-report` |
| 프로필 시스템 (N2) | **70%** | D2 | **4/4** profiles · feature 플래그 **전수 소속** (`owns`+`flags`) · `list-flags --profile`. F2 ✅ |
| Harness topology (N3) | **70%** | D3 | `parallel`·`producer_reviewer`·`pipeline` shipped (`topic_router.py`). adversarial = LC-L4 별도 |
| Trust-gated 자율성 (L1~L2) | **65%** | D2 | auto_approve_gate·trust_budget + **N4 v1/v2** ladder SSOT, header dial, Human ceiling PATCH, demotion inbox (T-A0), F8 quarter demote→L0. L3 자동화·KPI escalation_rate는 후속 |
| S2 episode 힌트 | **5%** | D0 | **동결** — 전역 bandit 목표 제외. S1.5 explore·episode lift 관측만 |
| S3 외부 능력 통합 | **15%** | D0~D1 | plugin_discovery·mcp_tool_contract·skill_drafts 부품 존재, 루프 없음. 인터페이스 설계만 선행(N7) |
| 컨텍스트 품질 (repo_map·compaction) | **55%** | D2 | 구현+self-eval+F7 프로토콜/계측 완료. **실세션 7일 dogfood 실행·ON/OFF 결정**만 남음 |
| 관측·평가 (eval harness·bench·KPI) | **70%** | D3 | 도구 풍부(emergence bench, feedback report, dogfood suite). 남은 것: 지표→의사결정 연결의 정례화 |
| Frontend Mission OS | **75%** | D3 | Phase D ✅ (hooks + client split) · **N4 v2** dial/picker · synthesize_only path · §3.2.1 light discuss |
| OpenAI-compat API (N9) | **35%** | D1 | 라우터 존재. 소비자·문서·감사 헤더 등 서사 완성 없음 |
| 슈퍼 샘플 준비도 (Layer 3) | **20%** | D0~D1 | 내부 문서는 풍부하나 외부인용 quickstart·fork 가이드·공개 재현 리포트 없음. 패키징 baseline만 존재 |

### 3.2 구조적 결함 (F1~F12) — %가 아니라 구조가 문제인 것

- **F1. Default-OFF 무덤:** 완성의 정의가 "코드 존재"에 머물러, 창발·S1 등 핵심 기능이 플래그 OFF로 죽어 있다. 측정 없이 쌓인 D1 코드는 자산이 아니라 재고다. → **처방:** D0~D4 사다리 채택(§1), 신규 기능은 "D3 도달 계획" 없이 착수 금지, S1 dogfood부터 소진.
- **F2. 플래그 스프롤 가속:** ✅ feature 플래그 전수 프로필 소속 (`run/profile.py` `owns`+`flags`, `feature_flags_without_owner()==[]`). 신규 feature 플래그는 최소 1개 프로필 `owns`/`flags`에 추가 (`test_f2_every_feature_flag_has_owner`). 만료 조건(승격/제거 시점) 메타는 잔여.
- **F3. 문서-코드 괴리:** N2 SSOT는 **`run/profile.py`** (app_config 아님). TRACEABILITY partial vs “shipped” 과대 주의. → **처방:** 게이지가 단일 진실; §3.3 [선행] 태그; **코드 SSOT 이름 그대로** (`s1_flags.py`, `topic_router.py`, `run/profile.py`).
- **F4. run_meta 이중 상태 함정:** ✅ 규칙+CI — CLAUDE.md / AGENTS.md · turn-end replay · `stamp_run_meta()` · `tests/test_run_meta_write_discipline.py`. **allowlist empty** (in-memory `run_meta[` writers eliminated).
- **F5. 인프라/도메인 혼재:** ✅ 결정 — [F5-TRADING-ISOLATION.md](./F5-TRADING-ISOLATION.md). `trading_mission/`·`quant/` extension lane; 코어 PR trading delta 0; 경계 `extensions/quant_trading.py`. 물리 이동은 defer.
- **F6. 프론트 상태 부채:** ✅ Phase D — RoomChat hooks (`useRoomComposerPrefs` · `useRoomSlashCommands` · `useRoomRunWatchdog` · `useRoomRecoveryLifecycle`) + `api/client` domain split (`http` · `workspaceClient` · `missionGatewayClient` · `wsClient`). N4 dial은 그 위에 탑재됨.
- **F7. 품질 평가의 mock 편중:** repo_map·compaction이 "실세션 평가 불가"로 OFF에 갇힘. → **처방 준비 ✅:** [F7-REPO-MAP-COMPACTION-DOGFOOD.md](./F7-REPO-MAP-COMPACTION-DOGFOOD.md) · `make f7-dogfood-env` / `make f7-dogfood-report` · `last_context_bundle`/`context_quality_log` 계측. **실행:** 7일 supervisor dogfood → ON/OFF (방치 금지).
- **F8. 비용·크레딧 가시성 부재:** 세션 `cost_ledger`는 존재. → **처방 준비 ✅:** [F8-COST-VISIBILITY.md](./F8-COST-VISIBILITY.md) · `.agent-lab/cost_ledger_quarter.json` · `AGENT_LAB_QUARTER_BUDGET_USD` · 초과 시 autonomy **L0 demotion** · `make f8-cost-report` · runtime `cost_quarter`.
- **F9. Hot-path 갓 모듈·갓 컴포넌트:** 실측(2026-07-04) — `plan/execute.py` 1691 · `plan/workflow.py` 1281 · `room/turn_flow.py` 1084(단일 `run_room` **~471줄**, `continue_room_round` ~428줄) · `web/RoomChat.tsx` **3497줄**(useState 30·useEffect 34·useRef 16). **F6 Phase D는 훅 4개 추출 + client split에 한정** — RoomChat 본체·`run_room`은 미해소. → **ratchet 가드 ✅:** `structure_metrics.py` `hot_path_py_files` baseline(1691·1281·1084) + `large_tsx_files`(RoomChat 3497) — `make structure-metrics-check` / `tests/test_structure_metrics.py`. **잔여:** ADR §3.5 Stage 3 분해(`run_room` phase 3함수 · RoomChat 뷰·상태 분리 — 병행 가능) · **`workflow.py`·`execute.py` 분해는 §3.5.1 P1(plan authority 확정) 선행 필수**. **모트:** Oracle·worktree 불변.
- **F10. 플래그·레지스트리 드리프트:** 실측 `AGENT_LAB_*` **215개**(본문 "212개" 표기와 불일치), `runtime_flags` 레지스트리 157개 → **~58개가 레지스트리 밖**. 단일 참조 플래그(`EMERGENCE_BENCH_LIVE`·`SKIP_LIVE` 등) 잔존. F2는 "프로필 소속"만 강제하고 "레지스트리 등재"는 미강제 → 문서 하드코딩 수치가 굳어 **F3 재발 씨앗**. → **처방 (구현 지점):** ① 문서의 플래그 개수 하드코딩 제거 → "`make list-flags` 참조"로 치환 (본문 ✅ 2026-07-04) ② 레지스트리 = `src/agent_lab/runtime_flags.py` — grep 실측(`grep -rhoE "AGENT_LAB_[A-Z0-9_]+" src/agent_lab | sort -u`)과 레지스트리 등재분의 차집합 0 가드를 `tests/test_runtime_flags_registry.py`(신규)로 추가, 기존 예외는 명시 allowlist로 시작해 소진. **모트 중립.**
- **F11. 상태 god-dict (타입 없는 `run_meta`):** 실측(2026-07-04) — `run.json`은 `dataclass`/`TypedDict`/`pydantic`이 아닌 자유 `dict[str, Any]`이고 `run_meta: dict[str, Any]`가 **362개 함수 시그니처**에 흐름. `run/schema.py`(78줄) `validate_run()`은 런타임 dict 검사일 뿐 타입 아님. **F4는 쓰기 규율만 잡음** — "문자열 키 가변 자루가 1급 자료구조"라는 설계 자체가 잔존 → 단일 최대 부채(루프 correctness 추론·부분 테스트·리팩터 저해). → **처방:** ADR §3.5 Stage 1 — 경계에서 `RunState` 타입으로 감싸고 안쪽부터 조임. **모트 강화**(감사·재현성). **목표:** D0(설계) → 점진 D2.
- **F12. 레이어 순환 (매듭):** 확정된 양방향 import — `runtime` ↔ `room`(runtime→`room.hooks`/`objections`/`sse_stream`, room→`runtime.events`/`invoke_execute`/`policy`), 겹쳐서 `room`↔`plan`·`runtime`↔`mission`. **runtime/room/plan/mission = 폴더로만 쪼갠 하나의 덩어리.** Makefile 31개 `audit-*-imports`+`typecheck-*-ratchet`은 이 매듭을 순찰하는 흉터 조직 — 경계 미획정의 증거. 파사드도 샘(`room/__init__.py` 104 export 중 ~30개가 `_`-내부). → **처방:** ADR §3.5 Stage 2 — 의존성 0 `agent_lab.core`(도메인 타입 + 루프-as-data) 추출, 단방향 의존. 31 ratchet → 1개 no-cycle 가드로 대체. **모트 중립.** **목표:** D0 → D2.

### 3.2.1 Room preset · discuss 지연 — dogfood 관찰 (2026-07)

프로파일 근거: fast preset codex+cursor ~54s (codex만), supervisor 동일 조합 ~281s (3× agent invoke). SSE TTFB ~0.34s · mock preamble ~32ms — 지연은 Room Python이 아니라 **preset 토폴로지 + 실 agent CLI** 쪽.

| 관찰 | 현재 동작 | 상태 |
|------|-----------|------|
| **Fast + 2 agents** | roster>1이면 **fast→supervisor 승격** (`resolve_preset_for_roster`); UI도 `forceRoomPreset("supervisor")`. silent truncate 제거 | ✅ §3.2.1 |
| **Supervisor 단순 discuss** | `mode=discuss` + loop → **light discuss**: `consensus_mode=False`, `agent_rounds=1`, runtime `analyze`, **`discuss_light` → lead-last OFF(전원 동시 1 wave)**. plan/합의/peer-review는 lead-last 유지 | ✅ §3.2.1 |

관련: [ROOM-TRANSCRIPT-CONTRACT.md](./ROOM-TRANSCRIPT-CONTRACT.md) §3 (pending UI는 1a에서 수정) · N3 room_preset · [05-room-agent-roles.md](./05-room-agent-roles.md) §Fast preset.

### 3.3 실행 로드맵 (wave 1a·1b·1c)

| 시기 | [선행] | 할 일 (실행 수준) | 닫힘 / 관측 |
|---|---|---|---|
| **지금** | **2026-07 code wave ✅** (아래) | S1 dogfood — §1 **S1 관측 절차** 1~4를 supervisor 실미션마다 반복 | `by_source.history.n`·`advisor_lift.history_vs_default` 기록 축적 (formal closure 없음) |
| **~1달** | F7 protocol ✅ · **dogfood 시작 2026-07-05** | 7일 경과(2026-07-12) 후 `make f7-dogfood-report` | Decision table 기준으로 두 플래그 ON/OFF 확정 커밋 |
| **분기** | S1 data · F8 instrumented ✅ | ① env `AGENT_LAB_QUARTER_BUDGET_USD` 실값 설정 → `make f8-cost-report` 정례화 ② §2.5 매트릭스 재검토 ③ §1.4 KPI 리뷰 ④ N5/S2 재평가 ⑤ dogfood-first 만료 검토 (`by_source.history.n` ≥ 30) | §3.1 D 단계 갱신 (판정 근거 병기) |
| **동결** | — | N5 전역 bandit · N6~N7 · Gateway · trading core | explicit Human OK 없이 착수 금지 |

**의존성 요약:** N4 ← F6 필수, N2 권장 · N5 ← S1 dogfood + S1.5 D2+ (전역 bandit 없음) · N8 ← emergence-bench 프로토콜

### 3.3.1 2026-07 code wave (shipped)

구현 백로그(코드) — dogfood **실행**은 운영 트랙.

| ID | 산출 |
|----|------|
| **Phase 1c / F6** | RoomChat hooks · `api/client` domain split |
| **N4 v1/v2** | `autonomy_ladder` · `/autonomy` GET/PATCH · dial · demotion inbox T-A0 |
| **N2 / F2** | `run/profile.py` 4 profiles · feature flag **전수** `owns`/`flags` · `list-flags --profile` |
| **F4** | `stamp_run_meta` · write-discipline allowlist **empty** |
| **F5** | [F5-TRADING-ISOLATION.md](./F5-TRADING-ISOLATION.md) — extension lane, core trading delta 0 |
| **§3.2.1** | fast→supervisor roster promote · light discuss · full-parallel R1 |
| **Phase 2** | dead-code contracts · `synthesize_only` dedicated path (`runSynthesizeOnly`) |
| **F7 prep** | [F7-REPO-MAP-COMPACTION-DOGFOOD.md](./F7-REPO-MAP-COMPACTION-DOGFOOD.md) · `make f7-dogfood-*` |
| **F8 prep** | [F8-COST-VISIBILITY.md](./F8-COST-VISIBILITY.md) · quarter ledger · L0 demote · `make f8-cost-report` |

**남은 것 (코드 외):** supervisor/F7 **실사용** · 분기 KPI · 동결 항목.

### 3.4 코드 감사 — 3축 피드백 (2026-07-04)

실측 기반 감사. 수치는 `find`/`grep`/`.venv pytest`/`structure_metrics.py`로 검증. 결론: **코드 자산은 충분, 이제 병목은 코드가 아니라 (a) 소수 hot-path의 비대화, (b) 런타임 증거의 부재**다.

**축 1 — 코드 구조 복잡성:** 규모는 크나(py 347파일·75k LOC·root 116모듈·subpkg 22 / tsx 302파일·27k LOC) 규율 도구는 상위권 — import audit 14종 + typecheck ratchet 17종 + `structure-metrics`. **문제는 스프롤이 아니라 국소 집중:** 상위 3개 hot-path(`execute.py`·`turn_flow.py`·`RoomChat.tsx`)가 복잡도를 독점 → **F9** 신설. Makefile 114 targets/481줄의 per-module ratchet은 좋은 방어지만 그 자체가 유지 표면 — 패키지 분리가 아직 소화되지 않았다는 신호.

**축 2 — 동적 작동(정확성·효율·자율):**
- **효율 ✅ 규명:** §3.2.1 — 지연은 Room Python 아닌 preset 토폴로지+agent CLI(supervisor 281s vs fast 54s). light discuss로 대응 완료.
- **정확성 ⚠ 테스트성:** `run_room`(~471줄 단일 함수)이 합의·턴 correctness의 핵심인데 분해가 안 돼 회귀 표면이 큼(→ F9).
- **자율 ⚠ 미증명:** L0~L2 코드화(N4)는 됐으나 **L3 자동화·`escalation_rate_by_level`은 후속**(§3.1). S1 루프는 supervisor scope만 ON이고 **lift 미측정** — `make feedback-report` 실행 전까지 "동적 자기발전"은 코드일 뿐 증거 없음(F1 그림자).

**축 3 — 슈퍼샘플 대비 완성도·안정성·퀄리티:**
- **안정성 ✅:** `.venv` 2824+ 테스트 수집, mock-only CI, smoke 37 — fork 리더 신뢰 기반은 견고.
- **완성도 ⚠:** Layer 3 = 20%. `QUICKSTART`/`FORK` 가이드 **부재**, `fork_time_minutes` 계측 없음 → T1(재현 신뢰) 미달. README(237줄)는 있으나 "15분 mock 미션 완주" 경로 없음.
- **퀄리티 갭의 본질:** 경쟁 샘플과의 차이는 **기능이 아니라 "증명 가능"** 다리(§1 Layer 3) — 창발이 성능을 올린다는 **공개 재현 리포트가 없음**. 여기에 RoomChat 3497줄이 겹쳐 "벗겨갈 만한 원본" 문턱을 낮춤.

**우선순위(개선 액션 — 코드 외 실행 트랙과 정합):**

| P | 액션 | 결함/이니셔티브 | 닫힘 기준 |
|---|------|------------------|-----------|
| **P0** | `make feedback-report` 정기 실행 → S1 lift 관측 시작 | F1 · N1 | `by_source.history.n`·`clean_pass_delta` 기록 |
| **P0** | `eval "$(make f7-dogfood-env)"`로 7일 dogfood 시계 시작(시작일 SSOT 기록) | F7 | Decision table ON/OFF |
| **P1** | ~~hot-path LOC ratchet(`structure-metrics-check`)~~ ✅ — `hot_path_py_files` 3종 + RoomChat `large_tsx_files` | **F9** | 가드 green (`test_structure_metrics_check_passes`) |
| **P1** | ~~문서 플래그 하드코딩 치환~~ ✅ → 잔여: 레지스트리 가드 `tests/test_runtime_flags_registry.py` | **F10** · F3 | 가드 green (예외 allowlist 소진 추적) |
| **P2** | 15분 mock 미션 QUICKSTART + `fork_time_minutes` 계측 | N8 · Layer 3 | clone→완주 재현 |
| **P2** | RoomChat shell 분리 ✅ (`SlashExecute` · `MainPane` · `EventStack` · popovers · inspector) | **F9** | `turn_flow` **675** · `RoomChat` **2252** |

**모트 체크:** P0~P2 전부 5모트를 **강화하거나 중립** — 측정(F1)·격리평가(F7)·가독성(F9)은 Oracle·worktree·Human Inbox를 약화시키지 않는다.

### 3.5 ADR — 코어 상태·제어 재아키텍처 (2026-07-04)

**결정:** 전면 rebuild **기각**. 코어 상태·제어 모델의 **점진적 재아키텍처(strangler-fig)** 채택. 대상 결함: **F11**(god-dict) · **F12**(레이어 순환) · F9(hot-path).

**근거 (super-sample / 프레임워크 대비 실측):**

| 축 | 잘된 에이전트 프레임워크 | Agent Lab 현재 | 갭 |
|---|---|---|---|
| 상태 | 타입 객체(LangGraph state·pydantic) | `dict[str, Any]` × 362 시그니처 | **큼** (F11) |
| 제어 | 그래프/상태머신 = 데이터 | 471줄 명령형 `run_room` | **큼** (F9) |
| 내구성 | 이벤트소싱·결정적 replay(Temporal류) | `completed_steps`+turn-end replay = 손제작 durable 일부 | 중간 |
| 레이어 | core ← orchestration ← adapters (DAG) | runtime↔room↔plan↔mission 순환 | **큼** (F12) |
| 어댑터 | 타입 노드/툴 인터페이스 | provider 관례(duck-typed); `ProviderSpec`은 frozen dataclass(메타만 타입) | 중간 |
| **모트** | 대개 없음 | **worktree·Oracle·execute gate·run.json 감사·Human Inbox** | **Agent Lab 우위** |

핵심 통찰: **이긴 칸(모트)은 손제작·실전 검증됨. 진 칸(상태·제어·레이어)은 프레임워크가 인프라로 공짜로 주는 것을 직접 구현하다 매듭이 된 것.** ⇒ 기성 엔진(LangGraph/Temporal)으로 substrate를 갈면 모트를 남의 추상화 위에 재구현해야 해 손해. **모트는 지키고 뼈대 성질(타입 상태·데이터화된 루프·DAG 레이어)만 흡수한다.**

**Rebuild가 정당화되는 유일 조건:** durable execution을 손수 유지하는 대신 기성 엔진으로 substrate 교체를 **전략적으로** 택할 때. 현 모트가 손제작·검증된 이상 **비추천** — 재평가는 §3.3 분기 행.

**실행 — 3-Stage strangler (전부 점진적, merge gate 아님):**

| Stage | 목표 | 결함 | 방법 (구현 지점) | 닫힘 |
|-------|------|------|------|------|
| **1** | `RunState` 타입화 | F11 (F4·F10 뿌리) | 신규 `src/agent_lab/run/state.py`에 `RunState` (`@dataclass` 또는 pydantic — mypy ratchet 정합 우선). **첫 경계 = `read_run_meta()`** (`run/meta.py:39`) 반환을 wrapping 후 호출자부터 안쪽으로 전환; `run/schema.py::validate_run`의 dict 검사를 타입 생성자로 흡수 | 측정: `grep -rc "run_meta: dict\[str, Any\]" src/agent_lab` — **baseline 362**에서 하강 관측 |
| **2** | 순환 절단 | F12 | 신규 `src/agent_lab/core/` (import 의존 **0** — 도메인 타입 + 루프-as-data: §2.3 루프의 단계 enum + 전이 테이블). runtime↔room 공유물(`events`·`policy` 타입, `hooks`·`objections` 인터페이스)을 core로 내리고 양쪽이 단방향 참조. no-cycle 가드 = `tests/test_no_layer_cycles.py`(신규 — import 그래프 DFS, F2/F4 가드 테스트와 같은 스타일) | no-cycle 가드 green → Makefile 31개 audit/ratchet를 1개 가드로 대체 |
| **3** | `run_room` 분해·파사드 축소 | F9 | `room/turn_flow.py::run_room`(613행~, ~471줄)을 turn phase 3함수(routing/consensus/harvest)로 분리 — §2.3 루프 화살표와 1:1 대응; `room/__init__.py` 104 export 중 `_`-prefix ~30개를 내부 import로 강등 | `structure-metrics-check` LOC 하강, 파사드 `_`-export 0 |

**의존성:** Stage 2 ← Stage 1(타입 있어야 루프-as-data 안전) · Stage 3은 1·2와 병행 가능 — 단 **`workflow.py`·`execute.py` 분해는 §3.5.1 P1 선행** (plan authority가 흔들린 채 LOC만 쪼개면 "plan 들어감" 정의 3개가 각자 존속). 각 Stage는 독립 PR 단위로 쪼개고, 매 PR마다 `make test-fast` + `python scripts/smoke_room.py` green 유지 (빅뱅 금지). **모트 체크:** Stage 1은 감사·재현성 **강화**, 2·3은 **중립** — 5모트 무손상.

### 3.5.1 Plan authority 재정의 — B(signal-only) + skill authority (2026-07-05 결정)

**결정:** **B — signal-only plan.** casual send는 preset 무관 **discuss-only** (fast/supervisor 동일). plan side-effect(Scribe·FSM)는 아래 authority 신호가 있을 때만 연다. preset이 plan lane을 잠그는 형태(supervisor = 항상 plan)는 제거한다. 추가로 plan/clarity/execute 진입 authority를 **GJC식 skill-intent**로 확장한다 ([GJC-ENTRY.md](./GJC-ENTRY.md) · [TURN-POLICY.md](./TURN-POLICY.md)).

**용어 (사전 지식 불필요):** *Scribe* = Room 토론 에이전트와 별개인 "대화→`plan.md` 정리" 전용 LLM 패스 (`room/plan_scribe.py`, 프롬프트 `agents/prompts.py::ROOM_SCRIBE`). 토론 4번째 멤버가 아니라 턴 종료 후 후처리.

**Authority 계약 — plan side-effect를 여는 것은 이 5개뿐:**

| # | Authority | 소스 (코드) | 상태 |
|---|-----------|-------------|------|
| 1 | FSM phase `DRAFT`/`REFINE` | `plan/workflow.py` (INTAKE→CLARIFY→DRAFT→PEER_REVIEW→REFINE→HUMAN_PENDING→APPROVED) · `tick_plan_workflow_after_turn` | ✅ 있음 |
| 2 | 합의 도달 + pending agreements | `turn_policy.py` scribe_trigger `consensus_reached` | ✅ 있음 |
| 3 | verified loop 종료 | scribe_trigger `verified_loop_done` | ✅ 있음 |
| 4 | Human 「지금 정리」 | scribe_trigger `synthesize_only` (UI 버튼 — 플래그 아님) | ✅ 있음 |
| 5 | **skill_intent (신규)** | slash/skill 호출(예: `/plan-draft`) · agent MCP `propose_build` · envelope `[PROPOSED:]` delta threshold | ⬜ P2 |
| — | ~~`legacy_plan_send`~~ (preset/`synthesize=true` hint) | `turn_policy.py:20` — **제거 대상** | ⬜ P1 |

**P1 — B 전환 (legacy plan flag 잔재 제거):**

| 대상 | 작업 |
|------|------|
| `room/turn_policy.py` | `legacy_plan_send` trigger 제거; supervisor casual send → `run_scribe=false` (fast와 동일) |
| `web/src/utils/roomComposerPrefs.ts:12` | `planComposeActive()` 삭제 (supervisor/loop → plan 강제 로직). 사용처 동반 정리: `useRoomComposerPrefs.ts`(58행 `composeMode` 유도·137행), `useRoomExecuteSend.ts:96`, `RoomChat.tsx` 2곳 |
| API hint | send payload의 `composeMode: "plan"` 전송 중단 (receipt는 `turn_kind`/`scribe_trigger` 기반으로 대체) |
| `room/turn_flow.py:285·447` | `mode = "plan" if synthesize` 분기 제거 — `synthesize` 파라미터를 synthesize_only 전용으로 축소 |
| 가드 | turn_policy 테스트: "casual send는 어느 preset에서도 scribe_trigger 없음" · UI 계약 테스트(`test_workspace_ui_contract.py` 등) 갱신 |

**P2 — skill_intent authority 배선:**

| 대상 | 작업 |
|------|------|
| `turn_policy.py` | `TurnSignals.skill_intent` 필드 + ScribeTrigger `"skill_intent"` 행 추가 |
| 소스 ① slash/skill | skill invocation → API로 intent 전달 → TurnSignals 주입 |
| 소스 ② MCP | `propose_build`(`inbox/mcp_policy.py` 경로) 호출을 FSM signal로 승격 |
| 소스 ③ envelope | `[PROPOSED:]` delta threshold 초과 시 signal (기존 objections 파이프 재사용) |
| FSM MCP | `plan_phase_advance` tool 신설 — gate owner 에이전트만 호출 가능, `HUMAN_PENDING`·execute 409는 서버 불변 |

**P3 — GJC식 이관 (clarity/execute):** phase 전환 권한을 서버 자동 tick에서 **skill/MCP 호출 우선**으로 이동, 서버 tick은 fallback + gate 검증으로 축소. clarity는 CLARIFY hold 유지하되 clarifier 질문 생성을 skill로 노출(`clarity.py` 4축 점수는 유지 — GJC deep-interview analog). execute는 `propose_build` → Human GO 흐름을 skill invocation으로 통일. **artifact 불변:** `plan.md`/`run.json` 유지, GJC `.gjc/` layout은 흡수하지 않음 (§2.5 GJC 행).

**F9와의 순서:** P1 완료 = `workflow.py`(1281)·`execute.py`(1691) 분해 경계 확정 조건. P1 전에 이 둘을 쪼개면 `legacy_plan_send`/preset 잠금/FSM tick이 서로 다른 "plan 들어감" 정의를 유지한 채 파일만 나뉘고, frontend `planComposeActive` ↔ backend TurnPolicy dual-run이 고착된다. `run_room`·RoomChat 분해(Stage 3)는 P1과 병행 가능.

**모트 체크:** Human gate 전부 불변 — plan approve·execute 409·Inbox·worktree·Oracle. casual send에서 Scribe가 덜 도는 것은 중립(비용 절감). skill_intent는 authority를 넓히지만 모든 side-effect는 여전히 gate 뒤에서만 실행된다.

---

## 4. 이 문서의 운영 방법

- **갱신 트리거:** ① 마일스톤(N1~N9) 하나가 D 단계를 넘을 때 §3.1 게이지 갱신 ② 분기마다 §2.5 샘플 매트릭스 재검토 (§3.3 분기 행) ③ 새 1급 개념이 필요해지면 §2.2 개정 (신중하게).
- **역할 분담:** 이 문서 = 방향+완성도의 단일 진실 / [STRATEGIC-DIRECTION-2026.md](./STRATEGIC-DIRECTION-2026.md) = 경쟁 분석 배경(이력) / [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md) = 기능 단위 shipped 상태.
- **판정 언어:** "완료"라는 말은 D3 이상에만 쓴다. D1은 "코드 존재", D2는 "mock 검증"이라고 부른다.
- **모트 체크:** 어떤 이니셔티브든 착수 전에 한 문장으로 답한다 — *"이 작업은 5모트 중 무엇을 강화하거나, 최소한 약화시키지 않는가?"*
