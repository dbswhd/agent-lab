# FINAL PLAN (pending approval) — agent-lab GJC 파이프라인 이식

**Run** `2026-06-18-pipeline-transplant` · deliberate (load-bearing FSM 빅뱅 + 공개 오케스트레이션) · Architect CLEAR/APPROVE + Critic APPROVE (1 pass). **Status: PENDING APPROVAL** — 소스 미변경, 실행 없음. Source spec: `.gjc/specs/deep-interview-agent-lab-pipeline-transplant.md`.

## Objective
agent-lab의 `mission_loop` 오케스트레이션을 명료화(CLARIFY)→합의(Room 융합)→목표추적 실행 단계 + 자율 모드 라우팅으로 재배선. HITL 승인 게이트와 KEEP/FUSE 자산(worktree 격리·Oracle 검증·Room·divergence·crash_recovery) 보존.

## ADR
- **Decision**: **Option A — 가산적·플래그 게이트(`AGENT_LAB_PIPELINE`) transition-table 확장.** 신규 `CLARIFY` 페이즈 + mode-router 가드 + run.json `goal_ledger` + Room 합의 게이트 + 전용 LLM scorer를 `runtime/transitions.py`의 선언적 `TRANSITION_TABLE`에 가산. 플래그 ON = 사용자가 원한 완비 파이프라인 END STATE, OFF = 현행 거동 byte-parity.
- **Drivers**: (1) load-bearing 머지 FSM 빅뱅의 비가역·silent-bug 리스크 → 가역성 필수; (2) 선언적 transition table + 기존 env-플래그 관행이 가산 확장을 저비용화; (3) HITL + KEEP/FUSE 보존.
- **Alternatives**: B 빅뱅 파괴적 재작성(사용자 문구) — END STATE는 동일하나 비가역·무안전망·1101 lane 상실·직전 분해투자 무위화로 **타당성 기각**; C 병행 신규 오케스트레이터 — 중복·이중 진실소스로 기각.
- **Why chosen**: A는 사용자의 full-rewire END STATE를 그대로 도달하되 경로를 가역적·검증가능하게 만든다. "빅뱅"을 *파괴적 재작성*이 아니라 *완비-가산 재배선*으로 재해석.
- **Consequences**: 안정화 전까지 OFF/ON 이중 경로(유지부채) → **플래그 제거 마일스톤(AC8)으로 영구화 방지**. 신규 페이즈/가드/핸들러는 기존 계약 테스트와 통합.
- **Follow-ups**: 플래그 default-on 전환 → OFF 경로/플래그 분기 삭제(AC8).

## Resolved deferrals
1. **합의 역할매핑**: 특정 Room 에이전트(Cursor/Codex/Claude)를 Planner/Architect/Critic에 1:1 매핑하지 않음. 합의 PHASE는 기존 `consensus_policy.py`+`room_consensus_rounds.py`를 엔진으로 재사용; "역할"은 합의 라운드/패스에 대응. Room 다중에이전트 토론 유지 + 합의-게이트 가드 신설.
2. **goal-ledger 저장소**: run.json + `patch_run_meta` 재사용, 선택적 `goal_ledger` 섹션 가산(신규 스토어 회피, ultragoal 네이티브 융합).
3. **mode-router 신호**: run.json 신호 기반 가드 — 구체 앵커(file path/issue#/수용기준)·ambiguity 점수·verified_loop 유무로 CLARIFY/CONSENSUS/EXECUTE 선택. 기존 ralplan-gate 구체-신호 탐지 재사용.
4. **빅뱅 vs 점진**: 해소 — 가산·플래그 게이트.
5. **세부 수용기준**: 아래.

## Acceptance Criteria
- AC1 (OFF-parity): `AGENT_LAB_PIPELINE` OFF에서 `make test-fast` 1101 passed/0 failed.
- AC2 (CLARIFY): ON + vague(앵커 無) → CLARIFY에서 전용 scorer 평가, 임계 아래로 DISCUSS/CONSENSUS 전이; 앵커 有 → CLARIFY 스킵.
- AC3 (모드 라우팅): 신호 기반 자율 모드 선택, run.json/로그에 관찰가능.
- AC4 (HITL): plan·merge 승인 게이트 모든 모드 보존(자동통과 無).
- AC5 (KEEP/FUSE): worktree·Oracle·REPAIR·crash_recovery가 ON에서도 동작(통합 테스트).
- AC6 (goal-ledger): run.json `goal_ledger` 추적 + `run_schema` 검증 + crash_recovery 호환.
- AC7 (전이 계약): 신규 페이즈/가드/행이 `test_runtime_transition_table` 통과(핸들러 importable).
- AC8 (플래그 제거 마일스톤): ON 안정화 후 default-on 전환 → OFF 경로·플래그 분기 삭제로 이중유지부채 종결.

## Pre-mortem (3, 완화)
1. OFF 회귀 → OFF-parity 1101 그린(AC1) 게이트. 2. CLARIFY 데드락 → 구체신호 스킵 + 타임아웃/라운드 캡 + circuit breaker Human override. 3. goal_ledger 스키마 파손 → 선택 가산필드 + run_schema 검증 + crash_recovery 호환 테스트.

## Test plan
Unit(신규 가드/scorer/goal_ledger 헬퍼) · Integration(ON 풀 파이프라인 전이 + Room 합의 게이트) · e2e(AGENT_LAB_MOCK_AGENTS=1 미션 CLARIFY→…→VERIFY 완주) · Observability(모드 라우팅 로깅; OFF-parity=1101 lane).

## 권장 실행 시퀀싱 (비실행)
1. 플래그 + OFF-parity 골격 → 1101 그린. 2. 전용 scorer + CLARIFY 가드. 3. mode-router 가드. 4. goal_ledger(run.json). 5. Room 합의 게이트. 6. (AC8) default-on → OFF 경로 삭제. 각 단계 fast lane 그린, 독립 일시정지 가능. 권장 실행: ultragoal.

## Out of scope
KEEP/FUSE 역량 대체; Human 게이트 제거/자동승인; GJC 런타임 의존.
