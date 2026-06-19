# Planner — agent-lab GJC 파이프라인 이식 (deliberate)

## Source
Deep-interview spec: `.gjc/specs/deep-interview-agent-lab-pipeline-transplant.md` (ambiguity 37%, BELOW_THRESHOLD_EARLY_EXIT — 잔여 gap을 ralplan 타당성 게이트로 이관). 확정 의도: mission_loop 오케스트레이션을 명료화→합의→목표추적실행 단계 + 자율 모드 라우팅으로 재배선, HITL 게이트·KEEP/FUSE 자산 보존.

## 결정적 타당성 사실 (코드 근거)
- `runtime/transitions.py`의 `TRANSITION_TABLE`은 **선언적 FSM**: `RuntimeTransition(event, from_phases, to_phase, handler, lane, guard)` 행들. 핸들러는 문자열 경로, 가드는 `GuardKind` Literal, 페이즈는 문자열.
- `mission_loop.mission_loop_env_enabled()` (`AGENT_LAB_MISSION_LOOP`)·`AGENT_LAB_MISSION_AUTORUN`·`AGENT_LAB_EXTERNAL_TOOLS` — 레포가 **주요 오케스트레이션을 env 플래그로 이미 게이팅**.
- ⇒ "통째 재배선"의 END STATE(4개 컴포넌트 완비 파이프라인)는 **테이블 행/페이즈/가드의 가산적 확장 + 플래그 게이트**로 도달 가능. 파괴적 재작성 불필요.

## Principles
1. **거동 보존 마이그레이션**: 플래그 OFF = 현행 동작 byte-parity(기존 1101 fast lane 그린 유지). 플래그 ON = 신규 파이프라인.
2. **HITL 불변**: plan 승인·merge 승인 Human 게이트는 자동통과 없이 모든 모드에서 보존.
3. **KEEP/FUSE 자산은 핸들러로 유지**: worktree 격리·Oracle 검증·Room·divergence·crash_recovery는 실행 레인 핸들러로 그대로 배선.
4. **선언적 테이블이 seam**: 신규 페이즈/가드/행 추가로 확장(파괴적 rewrite 금지).
5. **가역성**: 플래그로 즉시 롤백 가능, 안정화 후 플래그 제거 마일스톤.

## Decision Drivers
1. load-bearing 머지 FSM 빅뱅은 silent-bug·비가역 리스크 → 가역성 필수.
2. 선언적 transition table + 기존 env-플래그 관행이 가산적 확장을 타당하게 함.
3. HITL + KEEP/FUSE 자산 보존이 제품 정체성.

## Viable Options
### A — 가산적·플래그 게이트 transition-table 확장 (RECOMMENDED)
신규 페이즈 `CLARIFY`(DISCUSS 앞단) + mode-router 가드 + run.json 기반 goal-ledger + Room 위 합의 게이트를, `TRANSITION_TABLE` 신규 행 + 신규 `GuardKind` + 전용 LLM scorer로 추가하고 전체를 `AGENT_LAB_PIPELINE` 플래그로 게이팅. **사용자의 full-rewire END STATE(플래그 ON=완비 파이프라인)에 도달하되 경로는 가역적.**
- Pros: 현행 1101 lane을 OFF-parity로 안전망; 비가역 리스크 제거; 선언적 테이블에 자연스러움; 단계별 독립 검증; KEEP/FUSE 그대로.
- Cons: 한동안 OFF/ON 이중 경로(유지부채) → 플래그 제거 마일스톤 필요.

### B — 빅뱅 파괴적 재작성 (사용자 문구 그대로)
mission_loop FSM을 통째 교체.
- Pros: 즉시 단일 깨끗한 end state.
- Cons: load-bearing 머지 코드, 무가역, 거대 blast radius, silent-bug 고위험, 1101 lane 안전망 상실. **타당성 기각.**

### C — 병행 신규 오케스트레이터
구 FSM 옆에 신 FSM 병치.
- Cons: 대규모 중복, 두 진실 소스. 기각.

**채택: A.** "빅뱅"을 *파괴적 재작성*이 아니라 *완비-가산 재배선*으로 재해석 — 의도(전면 파이프라인) 보존 + 리스크(비가역) 해소.

## 이관 deferred 항목 해소
1. **합의 역할매핑**: Room agents(Cursor/Codex/Claude)를 Planner/Architect/Critic에 1:1 매핑하지 않음. 합의 PHASE는 기존 `consensus_policy.py`+`room_consensus_rounds.py`를 엔진으로 재사용하고, "ralplan 역할"은 특정 에이전트가 아니라 **합의 라운드/패스**에 대응. Room 다중에이전트 토론 유지 + 합의-게이트 가드 추가.
2. **goal-ledger 저장소**: 신규 스토어 대신 **run.json + patch_run_meta 재사용**(기존 mission_loop 영속화 경로). 선택적 `goal_ledger` 섹션 가산 → ultragoal 개념을 네이티브 융합.
3. **mode-router 신호**: run.json 신호를 읽는 가드/분류기 — 구체 앵커(file path/issue#/수용기준)·ambiguity 점수·verified_loop 유무로 CLARIFY/CONSENSUS/EXECUTE 모드 선택. 기존 ralplan-gate 구체-신호 탐지 패턴 재사용.
4. **빅뱅 vs 점진**: 해소 — 가산·플래그 게이트(A).
5. **세부 수용기준**: 아래 AC.

## Acceptance Criteria
- AC1 (OFF-parity): `AGENT_LAB_PIPELINE` OFF에서 `make test-fast` 1101 passed/0 failed 유지(현행 거동 불변).
- AC2 (CLARIFY): ON + vague 작업(구체 앵커 無) → mission이 `CLARIFY` 페이즈에서 전용 scorer로 모호성 평가, 임계 아래로 떨어지면 DISCUSS/CONSENSUS로 전이. 구체 앵커 有 → CLARIFY 스킵.
- AC3 (모드 라우팅): 오케스트레이터가 신호 기반으로 모드 자율 선택; 결정이 run.json/로그에 관찰가능.
- AC4 (HITL): plan 승인·merge 승인 게이트가 모든 모드에서 자동통과 없이 유지.
- AC5 (KEEP/FUSE): worktree 격리·Oracle 검증·REPAIR·crash_recovery 경로가 ON에서도 동작(통합 테스트).
- AC6 (goal-ledger): goal 진행이 run.json `goal_ledger`로 추적; run_schema 검증 통과; crash_recovery 호환.
- AC7 (전이 테이블): 신규 페이즈/가드/행이 transition-table 계약 테스트(`test_runtime_transition_table`) 통과.

## Pre-mortem (3)
1. **OFF 회귀**: 플래그 분기가 현행 경로를 미세 변경. *완화*: OFF-parity = 기존 1101 lane 그린(AC1)을 게이트로.
2. **CLARIFY 데드락**: 신규 명료화 페이즈가 미션을 멈춤. *완화*: 구체-신호 스킵 + 타임아웃/라운드 캡 + Human override(circuit breaker 재사용).
3. **goal_ledger 스키마 파손**: run.json 검증/크래시복구 깨짐. *완화*: 선택적 가산 필드 + `run_schema` 검증 + crash_recovery 호환 테스트.

## Expanded Test Plan
- Unit: 신규 가드(`clarity_threshold_met`, mode-router) + scorer + goal_ledger 헬퍼.
- Integration: ON 풀 파이프라인 FSM 전이(CLARIFY→CONSENSUS→EXECUTE_QUEUE→…→VERIFY), Room 합의 게이트.
- e2e: 모킹 에이전트 미션을 CLARIFY→…→VERIFY 완주(AGENT_LAB_MOCK_AGENTS=1).
- Observability: 모드 라우팅 결정 로깅; OFF-parity = 1101 lane.

## 실행 시퀀싱 (핸드오프용, 비실행)
1. 플래그 + OFF-parity 골격(빈 CLARIFY 페이즈, 플래그 분기) → 1101 그린. 2. 전용 scorer + CLARIFY 가드. 3. mode-router 가드. 4. goal_ledger(run.json). 5. 합의 게이트(Room 재사용). 각 단계 fast lane 그린. 안정화 후 플래그 default-on → 제거.

## Out of scope
worktree/Oracle/Room/divergence 역량 대체; Human 게이트 제거/자동승인; GJC 런타임 의존.
