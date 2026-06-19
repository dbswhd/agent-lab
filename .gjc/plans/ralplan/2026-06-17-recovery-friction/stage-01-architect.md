# RALPLAN Architect Review — recovery-friction stage 1

## Verdict: WATCH / REQUEST CHANGES

## Steelman Antithesis
이 계획이 **올바른 마찰**을 고치는가? 계획 스스로 "진단 가정"으로 run-lock을 *추측*했다고 인정한다. "가장 강한 코드 증거"가 사용자의 실제 pain과 같다는 보장은 없다 — 사용자의 "execute·복구·마찰"은 worktree orphan 누적이나 verify/repair 루프 혼선, partial-turn 복구일 수 있고, run-lock 데드엔드는 작은 슬라이스일 수 있다. 즉 가치 입증이 약할 위험.
다만 — A는 **최저 리스크·최고 방어가능성** 슬라이스이고, 계획이 approval 게이트에서 redirect를 명시적으로 허용하므로, "틀린 것 빌드" 리스크는 승인 단계에서 차단된다. 이 점은 수용 가능.

## Tradeoff Tension (실재)
**구조화 이벤트 vs 하위호환.** run_lock_blocked 신규 type을 추가하되 기존 `error` 이벤트를 유지하면 클라이언트가 둘 다 받아 중복/혼선 가능; 대체하면 기존 error 컨슈머가 깨질 수 있다. 계획 R2가 "검토"라고만 함 — **명시적 결정**이 필요(권장: run_lock_blocked를 방출하고 기존 error는 호환 위해 유지하되, run_lock_blocked가 있을 때 클라이언트가 우선 처리하도록 계약 고정).

## 누락
- run-start 차단은 **두 경로**가 있다: SSE `generate()`(line ~134-138, sse error)와 result-dict 경로(line ~346-350, `result["error"]=...`). 계획이 SSE만 다루면 result-dict 경로는 여전히 bare. **둘 다** 일관 처리해야 함.
- `run_lock_recovery_hint`의 releasable 판정이 `maybe_release_orphaned_run_lock` 재시도 *후* 평가되는지(이미 해제됐으면 locked=False) 순서 명시 필요.

## Synthesis
A 방향 타당(안전·최소·즉시 가치, 진단 리스크는 approval로 차단). 단 (1) **하위호환 결정 고정**(run_lock_blocked 방출 + 기존 error 유지, 우선순위 계약), (2) **두 차단 경로(SSE + result-dict) 일관 처리**를 합격기준에 포함, (3) hint 평가가 orphan-release 재시도 후임을 명시 — 그러면 CLEAR.
