# RALPLAN Critic — recovery-friction stage 1

## Verdict: ITERATE

## 평가
- Principle–Option 일관성: 양호(A=안전·최소). 단 Architect 지적대로 하위호환 결정이 "검토"로만 남아 미확정.
- 대안 공정성: A/B/C + invalidation 제시 — 공정. 진단 가정도 정직하게 명시(좋음).
- 리스크 완화: R1(안전)·R3(오스코프) 구체적. 단 **두 차단 경로(SSE + result-dict)** 누락은 합격기준 불완전을 초래하는 치명 공백.
- 테스트 가능 합격기준: 4종 관측 가능. 단 result-dict 경로 합격기준 부재; 하위호환(기존 error 유지) 합격기준 부재.
- 검증 구체성: 레인 명시 — 양호.

## 수정 요구 (ITERATE 해소)
1. 하위호환 **명시 결정**: run_lock_blocked 방출 + 기존 error 이벤트 유지(우선순위 계약). 합격기준/테스트에 호환 포함.
2. **두 차단 경로 일관 처리**(SSE generate + result-dict)를 변경 목록·합격기준에 명시.
3. run_lock_recovery_hint 평가가 `maybe_release_orphaned_run_lock` 재시도 *후*임을 명시(이미 해제 시 locked=False, releasable 의미 명확).
4. 진단 오스코프 리스크는 approval redirect로 차단됨을 Consequences에 명시(이미 가정에 있으나 ADR로 승격).
