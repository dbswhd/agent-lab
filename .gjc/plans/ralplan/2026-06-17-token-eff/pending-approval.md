# RALPLAN Final Plan (pending approval) — 토큰 효율: 세션 비용 라이브 가시화 + 적응형 강등

합의: Planner→Architect→Critic, iteration 2 APPROVE. run-id 2026-06-17-token-eff.

## ADR
- **Decision:** 일반 room 런(discuss/team/divergence)에서 (1) 누적 토큰/USD를 **예산 설정과 무관하게 매 턴 SSE로 표면화**하고, (2) 예산(USD/토큰) 설정 시 over 전환에서 `efficiency_auto_enabled` 이벤트 + 다음 턴부터 기존 efficiency 모드 적응형 활성. 하드 정지는 mission/loop circuit-breaker(불변) + opt-in `AGENT_LAB_SESSION_HARD_CAP`에만.
- **Drivers:** 사용자 acute pain(경고 없는 토큰 초과) → 라이브 가시화 최우선; 인프라 재사용(cost_ledger/efficiency); mission/loop·회계 불변.
- **Alternatives considered:** A(가시화만) — 정보만 주고 지속 미해결; C(일반 런 하드 정지) — 대화형 세션을 죽임. 둘 다 단독 부족.
- **Why chosen (B):** 가시화(예산 독립) + over 시 명시적 적응형 강등으로 "오래 지속"을 비파괴적으로 해결하며 기존 트림/efficiency 인프라 재사용.
- **Consequences:** over 후 세션 동작 변화(축소 컨텍스트) → `efficiency_auto_enabled` 이벤트로 명시; adaptive_efficiency 플래그 run.json 영속(세션 재개 유지).
- **Follow-ups:** execute/복구 마찰(별도 차수); efficiency 기본값 재고; UI Run 탭 비용 위젯 폴리시.

## 구현 계획 (mock-only 검증)
1. `cost_ledger.py`: `session_budget_action(run_meta)` → `{cumulative:{tokens_in,tokens_out,usd}, surface:True, budget_set, warn, over, suggest_efficiency}`. budget_status(USD)와 신규 토큰 임계(`AGENT_LAB_SESSION_TOKEN_BUDGET`, cumulative tokens_in+out)를 OR(over=any). budget_set False면 warn/over False·cumulative/surface 채움. 기존 budget_status/record_agent_usage 미변경.
2. `room_turn_flow.py`: 턴 종료 후 항상 `on_event("budget_status", action)`. over 최초 전환 시 `run_meta["adaptive_efficiency"]=True` + `on_event("efficiency_auto_enabled", {reason, cumulative, threshold})` 1회. mission/loop 경로 미변경.
3. `room_turn_flow`/`continue_room_round` efficiency_mode 산출부: `effective_efficiency = efficiency_mode or bool(run_meta.get("adaptive_efficiency"))` → 기존 context_bundle/round 경로에 전달(트림 인프라 재사용, 신규 트림 로직 없음).
4. divergence 보호: 강등은 context trim에만 작용, `format_divergence_options` 옵션 수(2~4) 미변경.
5. `run.json`: 턴 스냅샷에 budget_status 요약 라운드트립.
6. opt-in `AGENT_LAB_SESSION_HARD_CAP=1`: 일반 런 over에서 `budget_exhausted` SSE + 정지(기본 off).

## Acceptance Criteria (mock, AGENT_LAB_MOCK_AGENTS=1)
- [ ] 예산 unset에서도 매 턴 `budget_status`(cumulative 토큰/USD) SSE 방출.
- [ ] 예산 설정+over 시 `efficiency_auto_enabled` 1회 + run_meta.adaptive_efficiency=True.
- [ ] adaptive_efficiency True → 다음 턴 effective_efficiency=True(run_room 산출부 OR).
- [ ] divergence 강등 시 옵션 수 2~4 유지.
- [ ] mission/loop circuit-breaker·loop_token_budget_exceeded 불변(회귀); under-budget 세션 불변(회귀).
- [ ] run.json budget 스냅샷 라운드트립.

## Test Plan
- Unit: session_budget_action 임계(USD/토큰, budget_set 유무, warn/over/none, over=any OR); effective_efficiency OR; run.json 라운드트립.
- Mock integration: cost over 주입 → budget_status + efficiency_auto_enabled + 다음 턴 efficiency 적용; under-budget → 변화 없음; mission circuit-breaker 회귀 1건.
- 레인: test-fast(unit) + test-integration(run).

## Non-Goals
비용 회계/가격 변경, 대화형 런 기본 하드정지, UI 재설계, execute/복구 마찰.

## Risks
- R1 행동 변화 → env 게이팅 + over에서만 강등 + efficiency_auto_enabled 명시.
- R2 mission/loop 이중 발화 → 일반 모드 경로 분기 가드.
- R3 SSE 노이즈 → 턴당 1회.
- R4 divergence 품질 → 트림 국한, 옵션 수 유지.
- R5 비결정성 → 명시 이벤트 + 세션 1회 전환 + run.json 영속.

## 상태: PENDING APPROVAL — 실행은 별도 승인 필요. 자동 실행/위임 없음.
