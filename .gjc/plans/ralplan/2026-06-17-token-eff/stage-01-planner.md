# RALPLAN Planner — 토큰 효율: 세션 비용 라이브 가시화 + 적응형 강등 (stage 1, short mode)

원천: 사용자 deferral 항목(토큰 효율) + 코드 실태. 확인: cost_ledger.py(record_agent_usage 전 모드 누적 + budget_status), turn_modes.loop_token_budget_exceeded(loop 한정), mission_loop circuit_breaker(mission 한정), context_limits.efficiency_*, deps.py(budget_status 노출), room_turn_flow.

## 문제 정의
실제 토큰/USD는 cost_ledger에 **모든 모드**에서 누적되지만, 초과 시 대응(circuit-breaker/일시정지)은 **mission·loop 모드에만** 존재한다. 일반 discuss/team/divergence 런은 비용이 사후 조회만 가능하고 **런 중 라이브 경고도, 누적 초과 시 적응형 강등도 없다** → 사용자가 경고 없이 토큰을 소진해 "오래 못 씀".

## Principles
1. 기존 회계 재사용: cost_ledger.budget_status / record_agent_usage / efficiency_mode를 그대로 쓰고 새 토큰 계산을 만들지 않는다.
2. 대화형(discuss/team/divergence)은 **강등하되 죽이지 않는다** — 하드 정지는 mission/loop 전용으로 유지(기존 circuit-breaker 불변).
3. 모든 게이팅은 env 구성 + 기본 비파괴(off 또는 보수적).
4. 라이브 가시성: 턴마다 budget_status를 SSE로 노출.

## Decision Drivers (top 3)
1. 사용자 acute pain = 경고 없는 토큰 초과 → 라이브 가시화가 최고 레버리지.
2. 재사용 vs 재발명: 인프라 완비, 갭은 일반 모드 wiring.
3. mission/loop circuit-breaker·비용 회계 불변(회귀 안전).

## Viable Options
**A — 수동 가시화만(passive).** 턴마다 budget_status SSE emit, 자동 강등 없음.
- Pro: 최소, 행동 변화 0. Con: 초과를 알릴 뿐 막지 못함 → "오래 못 씀" 미해결.

**B — 가시화 + 일반 모드 적응형 efficiency 자동 강등. [CHOSEN]** 턴마다 budget_status SSE emit; warn 시 경고, over 시 다음 턴부터 efficiency_mode 자동 활성(적응형). 세션은 계속(더 저렴하게).
- Pro: "오래 지속" 직접 해결, 기존 efficiency 인프라 재사용, mission/loop 무손상. Con: 행동 변화 → env 게이팅·보수적 기본 필요.

**C — 일반 런 하드 토큰 캡(loop처럼 정지).** over 시 일반 런도 일시정지.
- Pro: 강한 보장. Con: 대화형 세션을 죽임 → 도그푸딩 UX 악화.

**Invalidation:** A는 정보만 주고 지속성 미해결. C는 대화형 세션을 죽여 Principle 2 위반. → **B 채택** (C식 하드 캡은 opt-in env로만 제공).

## Chosen Approach — 파일별 변경
1. `src/agent_lab/cost_ledger.py`: `session_budget_action(run_meta)` 헬퍼 추가 — 기존 budget_status(USD)에 토큰 임계(`AGENT_LAB_SESSION_TOKEN_BUDGET`, cumulative.tokens_in+out) 결합, `{surface, warn, over, suggest_efficiency}` 반환. 기존 budget_status·회계 미변경.
2. `src/agent_lab/room_turn_flow.py`: 턴 종료 후(_emit_divergence_options 인근, 두 dispatch 사이트) `on_event("budget_status", session_budget_action(run_meta))` emit; `over` 또는 warn 시 `run_meta["adaptive_efficiency"]=True` 설정(다음 턴 강등 신호). mission/loop circuit-breaker 경로는 미변경.
3. efficiency 적용 지점(`context_bundle`/`room_turn_flow`의 efficiency_mode 결정부): `efficiency_mode or run_meta.get("adaptive_efficiency")`로 OR 결합 — 기존 정적 플래그와 공존.
4. `run.json`: 턴 스냅샷에 budget_status 요약 포함(patch_run_meta 경유; cost_ledger는 이미 기록됨).
5. (opt-in) `AGENT_LAB_SESSION_HARD_CAP=1` 시 일반 런도 over에서 `budget_exhausted` SSE + 정지 — 기본 off.

## Acceptance Criteria (mock, AGENT_LAB_MOCK_AGENTS=1)
- [ ] discuss/team/divergence 런에서 턴마다 `budget_status` SSE 이벤트 방출.
- [ ] cumulative가 warn 임계 도달 시 warn 표면화; over 도달 시 다음 턴부터 efficiency 자동 활성(run_meta.adaptive_efficiency).
- [ ] mission/loop circuit-breaker·loop_token_budget_exceeded 동작 불변(회귀).
- [ ] budget 미초과 세션은 강등 없이 동일 동작(회귀).
- [ ] run.json에 budget 스냅샷 라운드트립.

## Test Plan
- Unit: session_budget_action 임계(USD/토큰, warn/over/none); adaptive_efficiency OR 결합; run.json 라운드트립.
- Mock integration: cost over 주입 → budget_status SSE + 다음 턴 efficiency 적용; under-budget → 변화 없음; mission circuit-breaker 회귀 1건.

## Non-Goals
비용 회계/가격 모델 변경, 대화형 런 기본 하드정지, UI 재설계, execute/복구 마찰(별도 차수).

## Risks + Mitigations
- R1 행동 변화(자동 강등): env 게이팅 + 보수적 기본 + over에서만 강등(warn은 경고만).
- R2 loop/mission 이중 발화: 일반 모드 경로가 mission/loop circuit-breaker와 중복 작동 안 하도록 분기 가드.
- R3 SSE 노이즈: 턴당 1회 emit.
- R4 efficiency 강등이 divergence 품질 저하: divergence는 over에서도 옵션 수는 유지(강등은 context trim에 국한).
