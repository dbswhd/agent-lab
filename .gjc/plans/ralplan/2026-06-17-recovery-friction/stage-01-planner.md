# RALPLAN Planner — execute/복구 마찰: run-lock 차단 경로 구조화 복구 신호 (stage 1, short mode)

원천: 사용자 deferral(execute/복구 마찰) + 코드 진단. 확인: run_control.py(try_begin_run→maybe_release_stale 600s, maybe_release_orphaned 90s/active==0, force_reset, run_lock_status), crash_recovery.py(G3 boot reconcile), app/server/routers/room.py(run-start 2곳에서 bare error), check_worktree_orphans.py(수동 스크립트), RecoveryStrip(프론트, P1d).

## 진단 가정 (명시)
execute/복구 인프라는 이미 성숙(자동 stale/orphan 해제, crash recovery, orphan 스크립트). 가장 강한 코드 증거의 잔여 인터랙티브 마찰 = **run 시작이 lock으로 막힐 때 bare error만 방출**(room.py: `sse({"type":"error","message":"a run is already in progress"})`, 2곳) → lock 나이·워커 수·복구 행동 신호 없음 → 데드엔드. RecoveryStrip은 구조화 신호가 있어야 act 가능. **만약 사용자의 실제 마찰이 다른 곳(worktree orphan 누적, verify/repair 혼선, partial-turn)이면 approval에서 redirect.**

## Principles
1. 복구 신호는 구조화·행동가능 — bare error 금지, RecoveryStrip이 release/cancel CTA를 띄울 수 있게.
2. 안전 우선: 진짜 활성 워커가 도는 run은 자동 해제하지 않음(기존 active==0/stale 보수 정책 유지).
3. 기존 복구 인프라(run_control, release-lock/cancel 엔드포인트) 재사용 — 새 복구 로직 최소.
4. 비파괴·additive: error 경로 보강만, 기존 동작·이벤트 호환 유지.

## Decision Drivers (top 3)
1. 사용자 acute 마찰 = run 시작 "이미 진행 중" 데드엔드(가장 흔한 인터랙티브 막힘).
2. RecoveryStrip은 존재하나 run-start 경로가 구조화 신호를 안 줌(연결 갭).
3. 안전(활성 run 오해제 금지) 보존이 절대 제약.

## Viable Options
**A — 구조화 `run_lock_blocked` 이벤트(surfacing). [CHOSEN]** run 시작 차단 시 bare error 대신 `{type:"run_lock_blocked", locked, age_sec, active_workers, releasable, action}` 방출. releasable은 기존 보수 정책(active==0 또는 stale)로만 판정.
- Pro: 최소·안전·즉시 가치(데드엔드→행동가능), RecoveryStrip 재사용. Con: 자동 해제는 안 함(사용자가 release CTA 눌러야).

**B — A + 인터랙티브 orphan 임계 env 튜닝.** 90s 하드코딩을 `AGENT_LAB_RUN_LOCK_ORPHAN_SEC`로.
- Pro: 자동성↑. Con: 임계 변경 리스크, 핵심 마찰(가시화)과 직교.

**C — execute/복구 전반 consolidation.** worktree orphan auto-clean + verify/repair surfacing + partial-turn 복구.
- Pro: 포괄. Con: 진단 불확실 + 범위 과대 + 리스크 큼.

**Invalidation:** C는 진단 불확실·범위 과대(가짜 작업 위험). B 단독은 안전 임계 변경이 핵심 가치(가시화)와 무관. → **A 채택**(B의 env 튜닝은 비파괴 옵션으로 동봉 가능, 기본 90s 유지).

## Chosen Approach — 파일별 변경
1. `src/agent_lab/run_control.py`: `run_lock_recovery_hint() -> dict` 추가 — `{locked, age_sec, active_workers, releasable, action}`. releasable = (not locked) or (active_workers==0) or (age_sec>=RUN_LOCK_STALE_SEC). action = release-lock 안내 문자열. 기존 release/status 함수 재사용, 정책 미변경.
2. `app/server/routers/room.py`: run-start 차단 2곳(현 bare error)에서 `maybe_release_orphaned_run_lock()` 재시도 실패 후 `sse({type:"run_lock_blocked", **run_lock_recovery_hint()})` 방출(+ 호환을 위해 기존 error도 후속 방출하거나 run_lock_blocked로 대체). 기존 release-lock/cancel 엔드포인트 미변경.
3. (opt) `AGENT_LAB_RUN_LOCK_ORPHAN_SEC` env로 orphan 임계 노출(기본 90s).

## Acceptance Criteria (mock, AGENT_LAB_MOCK_AGENTS=1)
- [ ] run 시작이 lock으로 막힐 때 `run_lock_blocked`(age_sec, active_workers, releasable, action) SSE 방출(bare error 단독 아님).
- [ ] orphan/stale lock이면 releasable=True + action이 release-lock 안내.
- [ ] 진짜 활성 run(active>0, age<stale)은 releasable=False(자동 해제 안 함, 안전).
- [ ] 기존 /room/runs/release-lock·/cancel 동작 불변(회귀).

## Test Plan
- Unit: run_lock_recovery_hint(unlocked/locked-orphan/locked-stale/locked-active) 판정.
- Mock integration: lock held 상태에서 run 시작 → run_lock_blocked 이벤트 shape; 활성 run releasable=False.
- 레인: test-fast(unit) + test-integration(이벤트).

## Non-Goals
활성 run 자동 강제 해제, worktree orphan auto-clean(별도 차수), verify/repair·partial-turn 변경, UI 재설계, crash_recovery(G3) 변경.

## Risks + Mitigations
- R1 활성 run 오해제: releasable 판정을 기존 보수 정책(active==0 또는 stale)에만 근거 — 새 해제 로직 없음.
- R2 기존 error 컨슈머 호환: run_lock_blocked는 신규 type; 기존 error 컨슈머가 깨지지 않게 호환 검토.
- R3 진단 오스코프(사용자 실제 마찰이 다른 곳): approval 게이트에서 redirect 가능하도록 진단 가정 명시.
