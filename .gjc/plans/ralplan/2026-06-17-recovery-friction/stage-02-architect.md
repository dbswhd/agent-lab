# RALPLAN Architect Re-review — recovery-friction stage 2

## Verdict: CLEAR / APPROVE

stage-01 3건 해소:
1. 하위호환 명시 결정 — run_lock_blocked 방출 + 기존 error 유지(우선순위 계약, graceful degrade). 구버전 컨슈머 안전.
2. 두 차단 경로(SSE generate + result-dict) 모두 단일 hint 소스로 일관 처리, 합격기준화.
3. hint 평가가 orphan-release 재시도 후임을 명시(locked=False면 정상 시작, 불필요).

진단 오스코프 리스크는 Consequences(ADR)로 승격되어 approval redirect로 차단됨이 명확.

## 비차단 관찰
- run_lock_recovery_hint의 age_sec/active_workers는 프로세스 전역 run_control 상태에서 읽으므로 단일 프로세스 가정과 일치(현 아키텍처). 멀티프로세스는 범위 밖(정상).
- result-dict 경로의 run_lock 힌트는 비SSE(클래식) 경로라 소비처가 제한적일 수 있음 — 그래도 일관성 위해 추가는 타당.

아키텍처 건전성 OK: 안전 정책 불변, 기존 복구 인프라 재사용, additive·하위호환, 진단 리스크는 승인 게이트로 관리.
