# RALPLAN Planner Revision — token-eff stage 2 (Architect+Critic 반영)

stage-01에 피드백 5건 반영. 변경분만 기재.

## 원칙 보강
- **가시화 ⟂ 예산:** 누적 토큰·USD(cost_ledger.cumulative)는 **예산 설정과 무관하게 매 턴 SSE로 항상 표면화**한다. 예산(USD/토큰)은 *추가* 신호일 뿐, 가시화의 전제 조건이 아니다.
- **예측가능성:** 적응형 강등이 켜질 때 별도 `efficiency_auto_enabled` SSE 이벤트로 사용자에게 명시한다(원인·임계 포함).

## 기본 동작 명문화 (비파괴)
- 기본: AGENT_LAB_MISSION_BUDGET_USD/AGENT_LAB_SESSION_TOKEN_BUDGET 모두 unset → **가시화만 항상 ON, 강등 없음**.
- 예산 설정 시: warn=경고 표면화, over=`efficiency_auto_enabled` + 다음 턴 강등.
- AGENT_LAB_SESSION_HARD_CAP=1(opt-in)일 때만 일반 런 over 정지(`budget_exhausted`). 기본 off.

## 파일별 변경 — 추가/정정
- `cost_ledger.py`: `session_budget_action(run_meta)` = `{cumulative:{tokens_in,tokens_out,usd}, surface:True(항상), budget_set:bool, warn:bool, over:bool, suggest_efficiency:bool}`. budget_set False면 warn/over는 False지만 cumulative/surface는 채워짐.
- `room_turn_flow.py`: 턴 종료 후 항상 `on_event("budget_status", action)`. `action["over"]` 최초 전환 시 `run_meta["adaptive_efficiency"]=True` + `on_event("efficiency_auto_enabled", {reason, cumulative, threshold})` 1회. mission/loop circuit-breaker 경로 미변경.
- **efficiency OR read 지점(명시):** `run_room`/`continue_room_round`에서 `efficiency_mode` 인자를 산출하는 지점에서 `effective_efficiency = efficiency_mode or bool(run_meta.get("adaptive_efficiency"))`로 결합해 기존 context_bundle/round 경로에 전달(컨텍스트 트림 인프라 재사용, 신규 트림 로직 없음). 회귀 테스트로 고정.
- **divergence 보호:** 강등은 context trim(recent_turns/pin/agreed 축소)에만 작용하고 `format_divergence_options`의 옵션 수(2~4)는 미변경 — 합격기준에 포함.
- `run.json`: 턴 스냅샷에 budget_status 요약 라운드트립.

## Acceptance Criteria 보강
- [ ] 예산 unset에서도 매 턴 `budget_status`(cumulative 토큰/USD 포함) SSE 방출.
- [ ] 예산 설정 + over 시 `efficiency_auto_enabled` 이벤트 1회 + run_meta.adaptive_efficiency=True.
- [ ] adaptive_efficiency True면 다음 턴 effective_efficiency=True(run_room 산출부에서 OR).
- [ ] divergence 강등 시 옵션 수 2~4 유지(트림만 적용).
- [ ] mission/loop circuit-breaker·loop_token_budget_exceeded 불변(회귀); under-budget 세션 불변(회귀).

## Risks 추가
- R5 비결정성(강등 후 동작 변화): `efficiency_auto_enabled` 이벤트로 명시 + over에서만(warn은 경고만) + 세션 1회 전환.
