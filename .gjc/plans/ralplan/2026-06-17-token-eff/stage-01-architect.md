# RALPLAN Architect Review — token-eff stage 1

## Verdict: WATCH / REQUEST CHANGES

## Steelman Antithesis
적응형 자동 강등(Option B)은 과설계일 수 있다. 사용자 pain은 "경고 없이 토큰 소진"이다 — 이는 (1) **기존 efficiency 모드를 기본 ON**으로 돌리거나 (2) **비용을 라이브로 보여줘 사용자가 수동으로 efficiency를 켜게** 하는 것만으로 상당 부분 해소된다. 즉 Option A(수동 가시화) + efficiency 기본값 재고가 B의 자동 강등 머신 없이도 핵심을 친다. B의 추가 가치(자동 지속)는 한계적일 수 있다.

## Tradeoff Tension (실재)
`adaptive_efficiency` 자동 활성은 **세션 내 비결정성**을 만든다 — 예산 교차 후 같은 세션이 갑자기 다르게(짧은 답·축소 컨텍스트) 동작해 대화 중 사용자를 혼란시킬 수 있다. "세션을 싸게 지속" vs "예측 가능한 동작" 사이 긴장. 강등이 켜질 때 **명시적 표면화**가 없으면 사용자는 품질 저하를 원인 모른 채 겪는다.

## 누락/불명확
- 계획이 **예산 미설정(기본) 시 동작**을 명확히 안 함. AGENT_LAB_MISSION_BUDGET_USD/SESSION_TOKEN_BUDGET 둘 다 unset이 기본 → warn/over가 영원히 안 뜸. 그러나 사용자 핵심 요구는 "비용을 본다"이므로, **예산 무관하게 누적 토큰/USD를 매 턴 표면화**해야 한다(가시화는 budget과 독립). 이 점이 명시돼야 함.
- efficiency 결정 read 지점 미특정: run_meta.adaptive_efficiency가 실제로 어디서 efficiency_mode와 OR되는지(run_room의 efficiency_mode 인자 산출부 vs context_bundle) 못박아야 회귀가 안전.
- 강등 발동 시 별도 surfacing 이벤트(`efficiency_auto_enabled`) 부재.

## Synthesis
B 방향 자체는 타당(가시화만으로는 "지속"을 보장 못 함). 단 (1) **라이브 가시화는 예산과 독립적으로 항상 동작**함을 명시, (2) 강등 발동 시 `efficiency_auto_enabled` 이벤트로 예측가능성 확보, (3) efficiency OR 결합의 정확한 read 지점 명시, (4) divergence 품질 보호(강등은 context trim에 국한, 옵션 수 유지) 확정 — 그러면 CLEAR.
