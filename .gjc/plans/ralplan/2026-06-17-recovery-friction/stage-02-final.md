# RALPLAN Final Plan (pending approval) — execute/복구 마찰: run-lock 차단 경로 구조화 복구 신호

합의: Planner→Architect→Critic, iteration 2 APPROVE. run-id 2026-06-17-recovery-friction.

## ADR
- **Decision:** run 시작이 run-lock으로 막힐 때 bare error 대신 구조화 `run_lock_blocked` 신호(lock 나이·워커 수·releasable·복구 action)를 방출해 RecoveryStrip이 release/cancel을 행동가능하게 surface. 안전 정책(활성 run 자동 해제 금지) 불변, 기존 error 이벤트는 호환 유지.
- **Drivers:** (1) run 시작 "이미 진행 중" 데드엔드가 가장 흔한 인터랙티브 마찰, (2) RecoveryStrip은 있으나 run-start가 구조화 신호 미제공(연결 갭), (3) 활성 run 오해제 금지(안전 절대 제약).
- **Alternatives considered:** B(orphan 임계 env 튜닝) — 핵심 가치와 직교+임계 변경 리스크; C(execute/복구 전반 consolidation) — 진단 불확실+범위 과대+리스크.
- **Why chosen (A):** 최저 리스크·최고 방어가능성, 안전 정책·기존 인프라 재사용, additive·하위호환. 진단 오스코프 리스크는 pending-approval 게이트의 redirect로 차단.
- **Consequences:** 진단 가정(run-lock=1순위 마찰)이 틀리면 승인 단계에서 redirect; run_lock_blocked 신규 이벤트로 데드엔드가 행동가능해짐; 멀티프로세스는 범위 밖(현 단일 프로세스 가정).
- **Follow-ups (별도):** worktree orphan auto-clean, verify/repair·partial-turn 복구 surfacing, orphan 임계 env 튜닝, Run-탭 복구 위젯 UI.

## 구현 계획 (mock-only 검증)
1. `src/agent_lab/run_control.py`: `run_lock_recovery_hint() -> dict` = `{locked, age_sec, active_workers, releasable, action}`. releasable = `not locked or active_workers==0 or (age_sec is not None and age_sec>=RUN_LOCK_STALE_SEC)`. action: releasable→release-lock 안내, 아니면 활성-run 대기/cancel 안내. 기존 run_lock_status/release 재사용, 정책 미변경.
2. `app/server/routers/room.py` (두 차단 경로):
   - SSE `generate()`(~134-138): `maybe_release_orphaned_run_lock()` 재시도 실패 후 `sse({"type":"run_lock_blocked", **run_lock_recovery_hint()})` 방출 **후** 기존 `error` 유지(우선순위 계약, graceful degrade).
   - result-dict(~346-350): `result["run_lock"] = run_lock_recovery_hint()` 추가 + 기존 `result["error"]` 유지.
   - hint는 orphan-release 재시도 *후* 평가.

## Acceptance Criteria (mock, AGENT_LAB_MOCK_AGENTS=1)
- [ ] SSE run-start 차단 시 `run_lock_blocked`(age_sec, active_workers, releasable, action) 방출 + 기존 error 유지.
- [ ] result-dict 경로 차단 시 `result["run_lock"]` 힌트 + 기존 error 유지.
- [ ] orphan/stale → releasable=True + action=release-lock; 활성(active>0, age<stale) → releasable=False.
- [ ] /room/runs/release-lock·/cancel·기존 error 컨슈머 동작 불변(회귀).

## Test Plan
- Unit: run_lock_recovery_hint 4케이스(unlocked / locked-orphan(active==0) / locked-stale / locked-active).
- Mock integration: lock held → run_lock_blocked + error 둘 다; result-dict run_lock 힌트; 활성 run releasable=False.
- 레인: test-fast + test-integration.

## Non-Goals
활성 run 자동 강제 해제, worktree orphan auto-clean(별도), verify/repair·partial-turn 변경, UI 재설계, crash_recovery(G3) 변경, 멀티프로세스 lock.

## Risks
- R1 활성 run 오해제 → releasable을 기존 보수 정책(active==0 또는 stale)에만 근거, 새 해제 로직 0.
- R2 기존 error 컨슈머 호환 → run_lock_blocked 신규 type + error 유지, 우선순위 계약.
- R3 진단 오스코프 → pending-approval redirect로 차단(ADR 명시).

## 상태: PENDING APPROVAL — 실행은 별도 승인 필요. 자동 실행/위임 없음.
## 진단 노트: 이 1차는 'run-lock 데드엔드'를 execute/복구 마찰의 최고-증거 슬라이스로 가정. 당신의 실제 마찰이 worktree orphan / verify·repair 혼선 / partial-turn 복구라면 승인 대신 redirect 해주세요.
