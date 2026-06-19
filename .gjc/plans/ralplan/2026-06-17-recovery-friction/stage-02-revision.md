# RALPLAN Planner Revision — recovery-friction stage 2 (Architect+Critic 반영)

stage-01에 피드백 4건 반영. 변경분만 기재.

## 하위호환 — 명시 결정
run-start 차단 시 **신규 `run_lock_blocked` 이벤트를 방출하고, 기존 `error` 이벤트(`"a run is already in progress"`)도 호환을 위해 유지**한다. 계약: 클라이언트가 `run_lock_blocked`를 받으면 그것을 우선 처리(release/cancel CTA), 못 받는 구버전은 기존 error로 graceful degrade. run_lock_blocked는 error보다 **먼저** 방출.

## 두 차단 경로 일관 처리 (명시)
run-start 차단은 두 경로 모두 처리:
1. SSE `generate()` (room.py ~134-138): `maybe_release_orphaned_run_lock()` 재시도 실패 후 → `sse(run_lock_blocked payload)` 방출 후 기존 error.
2. result-dict 경로 (room.py ~346-350): `result["run_lock"] = run_lock_recovery_hint()` 추가(기존 `result["error"]` 유지).
공통 payload는 `run_lock_recovery_hint()` 단일 소스에서 생성.

## hint 평가 순서 (명시)
`run_lock_recovery_hint()`는 `maybe_release_orphaned_run_lock()` **재시도 후** 평가한다. 재시도로 이미 해제됐으면 `locked=False`(이 경우 run이 정상 시작되어 hint 불필요); 여전히 막혔으면 locked=True + releasable(active==0 또는 stale)로 행동 안내.

## 파일별 변경 — 확정
1. `src/agent_lab/run_control.py`: `run_lock_recovery_hint() -> dict` = `{locked, age_sec, active_workers, releasable, action}`. releasable = `not locked or active_workers==0 or (age_sec is not None and age_sec>=RUN_LOCK_STALE_SEC)`. action: releasable면 "POST /api/room/runs/release-lock", 아니면 "활성 run 진행 중 — 대기 또는 cancel". 기존 status/release 함수 재사용, 정책 미변경.
2. `app/server/routers/room.py`: 위 두 경로에서 hint 사용(SSE: run_lock_blocked + 기존 error 유지; result-dict: result["run_lock"] 추가 + 기존 error 유지).

## Acceptance Criteria 보강
- [ ] SSE run-start 차단 시 `run_lock_blocked`(age_sec, active_workers, releasable, action) 방출 + 기존 `error` 이벤트도 유지(호환).
- [ ] result-dict 경로 차단 시 `result["run_lock"]` 힌트 포함 + 기존 `result["error"]` 유지.
- [ ] orphan/stale → releasable=True + action=release-lock; 활성(active>0, age<stale) → releasable=False.
- [ ] 기존 /room/runs/release-lock·/cancel·error 컨슈머 동작 불변(회귀).

## Consequences (ADR 승격)
- 진단 가정(run-lock이 1순위 마찰)이 틀릴 수 있으나, pending-approval 게이트에서 사용자가 redirect 가능 — "틀린 것 빌드" 리스크는 승인 단계에서 차단.
- run_lock_blocked 신규 이벤트 추가로 RecoveryStrip이 run-start 데드엔드를 행동가능하게 surface.

## Test Plan 보강
- Unit: run_lock_recovery_hint(unlocked / locked-orphan(active==0) / locked-stale / locked-active) 4 케이스.
- Mock integration: lock held → run_lock_blocked + error 둘 다; result-dict 경로 run_lock 힌트; 활성 run releasable=False.
