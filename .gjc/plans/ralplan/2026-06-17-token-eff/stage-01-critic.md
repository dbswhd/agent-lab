# RALPLAN Critic — token-eff stage 1

## Verdict: ITERATE

## 평가
- Principle–Option 일관성: 양호. 단 Architect 지적대로 "가시화는 예산과 독립" 원칙이 계획에 명시 안 됨 — 사용자 핵심 요구(비용을 본다)가 예산 설정에 종속되면 기본 상태에서 무용.
- 대안 공정성: A/B/C + invalidation 제시 — 공정. A에 "efficiency 기본값 재고" 변형이 빠졌으나 경미.
- 리스크 완화: R1~R4 구체적. 그러나 **강등 발동의 사용자 표면화(예측가능성)** 리스크가 누락 — 비결정성은 합격기준 신뢰를 위협하는 치명 공백.
- 테스트 가능 합격기준: 5종 관측 가능. 단 "예산 미설정 시에도 비용 표면화"와 "강등 발동 이벤트" 합격기준이 없음.
- 검증 구체성: 레인/회귀 명시 — 양호.

## 수정 요구 (ITERATE 해소)
1. 원칙/합격기준에 **예산 무관 누적 토큰·USD 매 턴 표면화** 추가(가시화 ⟂ 예산).
2. 강등 발동 시 `efficiency_auto_enabled` SSE 이벤트 + 합격기준/테스트 추가.
3. efficiency OR 결합의 정확한 read 지점(run_room efficiency_mode 산출부) 명시 + 회귀 테스트.
4. divergence 강등 시 옵션 수 유지(context trim 국한) 합격기준 명시.
5. 기본 동작 명문화: 예산 unset이 기본(비파괴) — 가시화만 항상 켜짐, 강등은 예산 설정 시에만.
